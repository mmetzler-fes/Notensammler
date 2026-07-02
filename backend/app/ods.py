"""Lesender und schreibender Zugriff auf eine ODS-Tabelle.

Die Implementierung arbeitet direkt auf ``content.xml`` (via lxml) und
kopiert alle übrigen Bestandteile des ODS-ZIP-Archivs unverändert. Dadurch
bleiben Formeln, Formatierungen und nicht angefasste Zellen erhalten.

Zellen werden über 0-basierte (row, col)-Indizes adressiert. Beim Schreiben
werden zusammengefasste Wiederholungen (``number-columns-repeated`` /
``number-rows-repeated``) nur so weit aufgesplittet, wie es nötig ist, um die
Zielzelle einzeln ansprechbar zu machen.
"""
from __future__ import annotations

import copy
import io
import shutil
import zipfile
from typing import Optional

from lxml import etree

NS = {
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
}


def q(prefix: str, local: str) -> str:
    return "{%s}%s" % (NS[prefix], local)


# --- Spalten-/Zellbezeichner ---------------------------------------------

def col_to_index(col: str) -> int:
    """'A' -> 0, 'B' -> 1, 'AA' -> 26 ..."""
    col = col.strip().upper()
    n = 0
    for ch in col:
        n = n * 26 + (ord(ch) - ord("A") + 1)
    return n - 1


def index_to_col(idx: int) -> str:
    idx += 1
    s = ""
    while idx:
        idx, r = divmod(idx - 1, 26)
        s = chr(ord("A") + r) + s
    return s


def cell_ref(row_idx: int, col_idx: int) -> str:
    """0-basierte Indizes -> A1-Notation (z. B. (8, 1) -> 'B9')."""
    return f"{index_to_col(col_idx)}{row_idx + 1}"


class Sheet:
    def __init__(self, table_el: etree._Element):
        self._el = table_el

    @property
    def name(self) -> str:
        return self._el.get(q("table", "name"))

    # -- interne Helfer ----------------------------------------------------
    def _rows(self):
        # Zeilen können direkt oder innerhalb von table-header-rows liegen.
        return self._el.iter(q("table", "table-row"))

    def _get_row(self, row_idx: int, create: bool = False) -> Optional[etree._Element]:
        """Liefert das (ggf. aufgesplittete) einzelne Zeilenelement für row_idx."""
        idx = 0
        for row in list(self._rows()):
            rep = int(row.get(q("table", "number-rows-repeated"), "1"))
            if idx <= row_idx < idx + rep:
                if rep == 1:
                    return row
                if not create:
                    return row
                return self._split(
                    row, q("table", "number-rows-repeated"), row_idx - idx, rep
                )
            idx += rep
        return None

    def _get_cell(self, row: etree._Element, col_idx: int, create: bool = False):
        idx = 0
        for cell in list(row):
            if cell.tag not in (
                q("table", "table-cell"),
                q("table", "covered-table-cell"),
            ):
                continue
            rep = int(cell.get(q("table", "number-columns-repeated"), "1"))
            if idx <= col_idx < idx + rep:
                if rep == 1 or not create:
                    return cell
                return self._split(
                    cell, q("table", "number-columns-repeated"), col_idx - idx, rep
                )
            idx += rep
        return None

    @staticmethod
    def _split(el, rep_attr, offset, rep):
        """Teilt ein wiederholtes Element in [pre][ziel][post] und gibt Ziel zurück."""
        parent = el.getparent()
        pos = parent.index(el)
        parent.remove(el)

        pieces = []
        if offset > 0:
            pre = copy.deepcopy(el)
            _set_rep(pre, rep_attr, offset)
            pieces.append(pre)
        target = copy.deepcopy(el)
        _set_rep(target, rep_attr, 1)
        pieces.append(target)
        post_count = rep - offset - 1
        if post_count > 0:
            post = copy.deepcopy(el)
            _set_rep(post, rep_attr, post_count)
            pieces.append(post)

        for i, p in enumerate(pieces):
            parent.insert(pos + i, p)
        return target

    # -- Lesen -------------------------------------------------------------
    def get_text(self, row_idx: int, col_idx: int) -> str:
        row = self._get_row(row_idx)
        if row is None:
            return ""
        cell = self._get_cell(row, col_idx)
        if cell is None:
            return ""
        return _cell_text(cell)

    def get_value(self, row_idx: int, col_idx: int):
        """Numerischer Wert falls vorhanden, sonst Text (str) bzw. ''."""
        row = self._get_row(row_idx)
        if row is None:
            return ""
        cell = self._get_cell(row, col_idx)
        if cell is None:
            return ""
        vtype = cell.get(q("office", "value-type"))
        if vtype == "float":
            raw = cell.get(q("office", "value"))
            if raw is not None:
                f = float(raw)
                return int(f) if f.is_integer() else f
        return _cell_text(cell)

    # -- Schreiben ---------------------------------------------------------
    def set_number(self, row_idx: int, col_idx: int, value: float):
        cell = self._ensure_cell(row_idx, col_idx)
        _clear_cell(cell)
        cell.set(q("office", "value-type"), "float")
        cell.set(q("office", "value"), _fmt_num(value))
        p = etree.SubElement(cell, q("text", "p"))
        p.text = _fmt_num(value)

    def set_text(self, row_idx: int, col_idx: int, value: str):
        cell = self._ensure_cell(row_idx, col_idx)
        _clear_cell(cell)
        if value != "":
            cell.set(q("office", "value-type"), "string")
            p = etree.SubElement(cell, q("text", "p"))
            p.text = value

    def _ensure_cell(self, row_idx: int, col_idx: int) -> etree._Element:
        row = self._get_row(row_idx, create=True)
        if row is None:
            raise IndexError(f"Zeile {row_idx + 1} existiert nicht im Blatt {self.name}")
        cell = self._get_cell(row, col_idx, create=True)
        if cell is None:
            raise IndexError(
                f"Spalte {index_to_col(col_idx)} existiert nicht in Zeile {row_idx + 1}"
            )
        return cell


def _set_rep(el, attr, count):
    if count <= 1:
        if attr in el.attrib:
            del el.attrib[attr]
    else:
        el.set(attr, str(count))


def _cell_text(cell) -> str:
    parts = [p.xpath("string()") for p in cell.findall(q("text", "p"))]
    return "\n".join(t for t in parts).strip()


def _clear_cell(cell):
    for child in list(cell):
        cell.remove(child)
    for attr in (
        q("office", "value-type"),
        q("office", "value"),
        q("office", "string-value"),
        q("table", "formula"),
    ):
        if attr in cell.attrib:
            del cell.attrib[attr]


def _fmt_num(value: float) -> str:
    f = float(value)
    return str(int(f)) if f.is_integer() else repr(f)


class OdsDocument:
    """Lädt ein ODS-Dokument, erlaubt Zugriff auf Blätter und speichert es."""

    CONTENT = "content.xml"

    def __init__(self, path: str):
        self.path = path
        with zipfile.ZipFile(path, "r") as zf:
            self._names = zf.namelist()
            self._members = {n: zf.read(n) for n in self._names}
            infos = {i.filename: i for i in zf.infolist()}
        self._infos = infos
        self._tree = etree.fromstring(self._members[self.CONTENT])

    def sheet_names(self):
        return [
            t.get(q("table", "name"))
            for t in self._tree.iter(q("table", "table"))
        ]

    def sheet(self, name: str) -> Sheet:
        for t in self._tree.iter(q("table", "table")):
            if t.get(q("table", "name")) == name:
                return Sheet(t)
        raise KeyError(f"Blatt '{name}' nicht gefunden")

    def remove_sheets_except(self, name: str):
        """Entfernt alle Blätter außer dem angegebenen (für den Export)."""
        for t in list(self._tree.iter(q("table", "table"))):
            if t.get(q("table", "name")) != name:
                t.getparent().remove(t)

    def to_bytes(self) -> bytes:
        """Serialisiert das Dokument als ODS-ZIP-Archiv (im Speicher)."""
        self._members[self.CONTENT] = etree.tostring(
            self._tree, xml_declaration=True, encoding="UTF-8", standalone=True
        )
        buf = io.BytesIO()
        # mimetype muss als erstes und unkomprimiert im Archiv stehen.
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            if "mimetype" in self._members:
                zf.writestr(
                    zipfile.ZipInfo("mimetype"),
                    self._members["mimetype"],
                    compress_type=zipfile.ZIP_STORED,
                )
            for name in self._names:
                if name == "mimetype":
                    continue
                zf.writestr(name, self._members[name])
        return buf.getvalue()

    def save(self, path: Optional[str] = None):
        """Schreibt atomar zurück (erst temporär, dann ersetzen)."""
        target = path or self.path
        data = self.to_bytes()
        tmp = target + ".tmp"
        with open(tmp, "wb") as fh:
            fh.write(data)
        shutil.move(tmp, target)
