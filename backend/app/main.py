"""FastAPI-Backend: Brücke zwischen Web-Frontend und der Gesamtnotenliste.ods.

Endpunkte:
  POST /api/login                       -> JWT gegen Blatt "Login_Daten"
  GET  /api/classes                     -> Klassen, die der Lehrer bearbeiten darf
  GET  /api/classes/{cls}/students      -> Schüler + für den Lehrer editierbare Spalten
  POST /api/classes/{cls}/grades        -> Noten schreiben (mit Sperre + Protokoll)
"""
from __future__ import annotations

import asyncio
import datetime as dt
from typing import List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import auth
from .config import settings
from .ods import OdsDocument, cell_ref, col_to_index, index_to_col

app = FastAPI(title="Notensammler")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serialisiert alle Datei-Zugriffe -> keine Race Conditions beim Speichern.
_file_lock = asyncio.Lock()


# --------------------------------------------------------------------------
# Hilfsfunktionen für den Aufbau der Klassenblätter
# --------------------------------------------------------------------------

def _open() -> OdsDocument:
    return OdsDocument(settings.ODS_PATH)


def _class_sheets(doc: OdsDocument) -> List[str]:
    return [n for n in doc.sheet_names() if n != settings.LOGIN_SHEET]


def _classteacher(sheet) -> str:
    ref = settings.CLASSTEACHER_CELL
    col = "".join(c for c in ref if c.isalpha())
    row = int("".join(c for c in ref if c.isdigit()))
    return str(sheet.get_value(row - 1, col_to_index(col))).strip()


def _scan_left_label(sheet, row_1based: int, col_idx: int) -> str:
    """Nächstgelegener nicht-leerer Eintrag links in der angegebenen Zeile.

    So werden über mehrere Spalten zusammengefasste Block-/Fach-Titel dem
    richtigen Feld zugeordnet.
    """
    start = col_to_index(settings.FIRSTNAME_COL) + 1
    for c in range(col_idx, start - 1, -1):
        txt = sheet.get_text(row_1based - 1, c)
        if txt:
            return txt
    return ""


def _summary_col_indices():
    """Spaltenindizes aller Schnitt-/Endnote-Spalten (aus der Konfiguration)."""
    idx = set()
    for pair in settings.SUMMARY_COLUMNS:
        for letter in pair:
            if letter:
                idx.add(col_to_index(letter))
    return idx


def _grade_columns(sheet, include_empty=False):
    """Notenspalten der Klasse.

    Standard: nur Spalten mit einem Lehrerkürzel in der Lehrer-Zeile.
    ``include_empty=True``: alle Spalten eines Blocks (mit Fach-Header in der
    Fach-Zeile), auch ohne Kürzel – aber ohne die Schnitt-/Endnote-Spalten.
    """
    cols = []
    teacher_row = settings.TEACHER_ROW - 1
    weight_row = settings.WEIGHT_ROW - 1
    subject_row = settings.SUBJECT_ROW - 1
    first = col_to_index(settings.FIRSTNAME_COL) + 1
    summary = _summary_col_indices()
    cls = sheet.name
    for c in range(first, settings.MAX_COL_INDEX + 1):
        owner = sheet.get_text(teacher_row, c).strip()
        if include_empty:
            # Spalte gehört zum Block, wenn sie einen Fach-Header ODER ein
            # Kürzel hat (Obermenge des Standardfalls); Summenspalten ausgenommen.
            if c in summary:
                continue
            if not owner and not sheet.get_text(subject_row, c).strip():
                continue
        elif not owner:
            continue
        block = _scan_left_label(sheet, settings.BLOCK_ROW, c)
        subject = _scan_left_label(sheet, settings.SUBJECT_ROW, c) or index_to_col(c)
        # Beschreibung: "Klasse · Block · Fach" (leere Teile werden ausgelassen)
        description = " · ".join(p for p in (cls, block, subject) if p)
        cols.append(
            {
                "col": index_to_col(c),
                "col_idx": c,
                "owner": owner,
                "label": subject,
                "block": block,
                "description": description,
                "weight": sheet.get_value(weight_row, c),
                "role": "grade",
            }
        )
    return cols


def _to_number(value):
    """Wandelt einen Zell-/Textwert in float um oder gibt None zurück."""
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        return None


def _compute_schnitt(sheet, schnitt_col_idx, grade_cols):
    """Berechnet den gewichteten Notenschnitt je Schülerzeile für eine Schnitt-Spalte.

    Entspricht der ODS-Formel: Summe(Note*Gewicht) / Summe(Gewicht), jeweils nur
    über die Teilnoten-Spalten desselben Blocks, bei denen Note und Gewicht
    gesetzt sind. Rückgabe: dict {Blattzeile(1-basiert) -> Anzeigetext}.
    """
    block = _scan_left_label(sheet, settings.BLOCK_ROW, schnitt_col_idx)
    members = [g for g in grade_cols if g["block"] == block]
    result = {}
    for r in range(settings.STUDENT_ROW_START - 1, settings.STUDENT_ROW_END):
        num = 0.0
        wsum = 0.0
        for g in members:
            grade = _to_number(sheet.get_value(r, g["col_idx"]))
            weight = _to_number(g["weight"])
            if grade is None or weight is None or weight == 0:
                continue
            num += grade * weight
            wsum += weight
        if wsum > 0:
            result[r + 1] = f"{num / wsum:.2f}".replace(".", ",")
        else:
            result[r + 1] = ""
    return result


def _summary_columns(sheet):
    """Schnitt- und Endnote-Spalten je Block (nur für den Klassenlehrer).

    ``role`` = "schnitt" (nur Anzeige) bzw. "endnote" (editierbar).
    """
    cls = sheet.name
    out = []
    for schnitt, endnote in settings.SUMMARY_COLUMNS:
        for col_letter, role, label in (
            (schnitt, "schnitt", "Schnitt"),
            (endnote, "endnote", "Endnote"),
        ):
            if not col_letter:
                continue
            c = col_to_index(col_letter)
            block = _scan_left_label(sheet, settings.BLOCK_ROW, c)
            description = " · ".join(p for p in (cls, block, label) if p)
            out.append(
                {
                    "col": col_letter.upper(),
                    "col_idx": c,
                    "owner": "",
                    "label": label,
                    "block": block,
                    "description": description,
                    "weight": "",
                    "role": role,
                }
            )
    return out


def _editable_columns(sheet, kuerzel: str, include_empty=False):
    """Spalten, die *dieser* Lehrer bearbeiten darf.

    Klassenlehrer (Zelle C3) dürfen alle Notenspalten bearbeiten, sonst nur
    die Spalten mit dem eigenen Kürzel in der Lehrer-Zeile. ``include_empty``
    blendet für den Klassenlehrer auch Spalten ohne Kürzel ein.
    """
    is_classteacher = _classteacher(sheet).casefold() == kuerzel.casefold()
    all_cols = _grade_columns(sheet, include_empty=include_empty and is_classteacher)
    if is_classteacher:
        return all_cols
    return [c for c in all_cols if c["owner"].casefold() == kuerzel.casefold()]


def _students(sheet, include_empty_names=False):
    """Schülerzeilen. Standard: nur Zeilen mit ausgefülltem Namen.

    ``include_empty_names=True``: alle Zeilen des Bereichs (z. B. damit der
    Klassenlehrer Namen ergänzen kann).
    """
    out = []
    nr_c = col_to_index(settings.NR_COL)
    name_c = col_to_index(settings.NAME_COL)
    vn_c = col_to_index(settings.FIRSTNAME_COL)
    for r in range(settings.STUDENT_ROW_START - 1, settings.STUDENT_ROW_END):
        nr = sheet.get_value(r, nr_c)
        name = sheet.get_text(r, name_c)
        vorname = sheet.get_text(r, vn_c)
        if not include_empty_names and name.strip() == "":
            continue
        out.append({"row": r + 1, "nr": nr, "name": name, "vorname": vorname})
    return out


def _meta_row_defs():
    """Vom Klassenlehrer editierbare Kopfzeilen je Notenspalte."""
    return [
        (settings.SUBJECT_ROW, "fach", "Fach", "text"),
        (settings.TEACHER_ROW, "kuerzel", "Lehrerkürzel", "text"),
        (settings.WEIGHT_ROW, "gewicht", "Gewicht", "number"),
        (settings.COMMENT_ROW, "kommentar", "Kommentar", "text"),
    ]


def _validate_weight(value) -> Optional[str]:
    s = str(value).strip()
    if s == "":
        return None
    try:
        f = float(s.replace(",", "."))
    except ValueError:
        return f"Gewicht '{s}' ist keine Zahl"
    if f < 0:
        return "Gewicht darf nicht negativ sein"
    return None


def _validate_grade(value) -> Optional[str]:
    """Normalisiert/prüft eine Note. Rückgabe: Fehlermeldung oder None."""
    if value is None:
        return None
    s = str(value).strip()
    if s == "":
        return None
    if s in settings.GRADE_ALLOWED_TEXT:
        return None
    norm = s.replace(",", ".")
    try:
        f = float(norm)
    except ValueError:
        return f"'{s}' ist keine gültige Note"
    if not (settings.GRADE_MIN <= f <= settings.GRADE_MAX):
        return f"Note {s} liegt außerhalb {settings.GRADE_MIN}-{settings.GRADE_MAX}"
    return None


# --------------------------------------------------------------------------
# Auth-Dependency
# --------------------------------------------------------------------------

def current_teacher(authorization: str = Header(default="")) -> str:
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Kein Token")
    token = authorization.split(" ", 1)[1]
    kuerzel = auth.decode_token(token)
    if not kuerzel:
        raise HTTPException(status_code=401, detail="Token ungültig oder abgelaufen")
    return kuerzel


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------

class LoginIn(BaseModel):
    kuerzel: str
    passwort: str


class GradeEntry(BaseModel):
    row: int          # 1-basierte Blattzeile
    col: str          # Spaltenbuchstabe
    value: str = ""   # Note als Text ("" = leeren)


class GradesIn(BaseModel):
    entries: List[GradeEntry]


# --------------------------------------------------------------------------
# Endpunkte
# --------------------------------------------------------------------------

@app.post("/api/login")
def login(data: LoginIn):
    doc = _open()
    try:
        sheet = doc.sheet(settings.LOGIN_SHEET)
    except KeyError:
        raise HTTPException(status_code=500, detail="Login-Blatt fehlt")
    k_col = col_to_index(settings.LOGIN_KUERZEL_COL)
    p_col = col_to_index(settings.LOGIN_PASSWORT_COL)
    kuerzel_in = data.kuerzel.strip()
    r = settings.LOGIN_FIRST_ROW - 1
    empty_streak = 0
    while empty_streak < 20:
        k = sheet.get_text(r, k_col).strip()
        if k == "":
            empty_streak += 1
            r += 1
            continue
        empty_streak = 0
        if k.casefold() == kuerzel_in.casefold():
            stored = sheet.get_text(r, p_col)
            if auth.verify_password(stored, data.passwort):
                return {"token": auth.create_token(k), "kuerzel": k}
            break
        r += 1
    raise HTTPException(status_code=401, detail="Kürzel oder Passwort falsch")


@app.get("/api/classes")
def list_classes(teacher: str = Depends(current_teacher)):
    doc = _open()
    result = []
    for name in _class_sheets(doc):
        sheet = doc.sheet(name)
        editable = _editable_columns(sheet, teacher)
        if editable:
            result.append(
                {
                    "class": name,
                    "is_classteacher": _classteacher(sheet).casefold()
                    == teacher.casefold(),
                    "editable_count": len(editable),
                }
            )
    return {"teacher": teacher, "classes": result}


@app.get("/api/classes/{cls}/students")
def get_students(
    cls: str,
    all_columns: bool = False,
    teacher: str = Depends(current_teacher),
):
    doc = _open()
    if cls not in _class_sheets(doc):
        raise HTTPException(status_code=404, detail="Klasse nicht gefunden")
    sheet = doc.sheet(cls)

    # Klassenlehrer sieht zusätzlich Schnitt (nur Anzeige) und Endnote (editierbar)
    # sowie die Kopfzeilen (Kürzel/Gewicht/Kommentar).
    can_edit_meta = _classteacher(sheet).casefold() == teacher.casefold()

    # "Alles anzeigen" (leere Spalten UND Zeilen ohne Namen) nur für den
    # Klassenlehrer.
    show_all = all_columns and can_edit_meta
    columns = _editable_columns(sheet, teacher, include_empty=show_all)
    if not columns:
        raise HTTPException(status_code=403, detail="Keine Bearbeitungsrechte")

    if can_edit_meta:
        columns = columns + _summary_columns(sheet)

    students = _students(sheet, include_empty_names=show_all)
    # aktuelle Werte je Schüler/Spalte
    grades = {}
    for st in students:
        row_idx = st["row"] - 1
        grades[st["row"]] = {
            c["col"]: _as_str(sheet.get_value(row_idx, c["col_idx"])) for c in columns
        }

    # Schnitt-Spalten selbst berechnen (Formel wird ohne LibreOffice nicht neu
    # berechnet), damit der Wert im Web korrekt und live aktuell ist.
    if can_edit_meta:
        all_grade_cols = _grade_columns(sheet, include_empty=True)
        for c in columns:
            if c["role"] != "schnitt":
                continue
            computed = _compute_schnitt(sheet, c["col_idx"], all_grade_cols)
            for st in students:
                grades[st["row"]][c["col"]] = computed.get(st["row"], "")

    def _is_editable(c):
        return c["role"] in ("grade", "endnote")

    public_cols = [
        {
            "col": c["col"],
            "label": c["label"],
            "block": c["block"],
            "description": c["description"],
            "owner": c["owner"],
            "weight": c["weight"],
            "role": c["role"],
            "editable": _is_editable(c),
        }
        for c in columns
    ]

    # Spaltenmittel ("Durchschnitt", Zeile 41): einfacher Mittelwert je Spalte
    # über die Schülerzeilen. Formel wird ohne LibreOffice nicht berechnet.
    footer = {}
    for c in columns:
        vals = [
            _to_number(grades[st["row"]].get(c["col"])) for st in students
        ]
        vals = [v for v in vals if v is not None]
        footer[c["col"]] = (
            f"{sum(vals) / len(vals):.2f}".replace(".", ",") if vals else ""
        )
    footer_label = sheet.get_text(
        settings.AVERAGE_ROW - 1, col_to_index(settings.NAME_COL)
    ) or "Durchschnitt"

    meta_rows = []
    meta = {}
    if can_edit_meta:
        # Kopfzeilen gelten nur für die Noten-(Teilnoten-)Spalten.
        grade_only = [c for c in columns if c["role"] == "grade"]
        for row, key, label, kind in _meta_row_defs():
            meta_rows.append({"row": row, "key": key, "label": label, "kind": kind})
            meta[row] = {
                c["col"]: _as_str(sheet.get_value(row - 1, c["col_idx"]))
                for c in grade_only
            }

    return {
        "class": cls,
        "columns": public_cols,
        "students": students,
        "grades": grades,
        "can_edit_meta": can_edit_meta,
        "all_columns": bool(all_columns and can_edit_meta),
        "meta_rows": meta_rows,
        "meta": meta,
        "footer_label": footer_label,
        "footer": footer,
    }


@app.post("/api/classes/{cls}/grades")
async def submit_grades(
    cls: str, data: GradesIn, teacher: str = Depends(current_teacher)
):
    async with _file_lock:
        doc = _open()  # frisch laden -> keine veralteten Daten überschreiben
        if cls not in _class_sheets(doc):
            raise HTTPException(status_code=404, detail="Klasse nicht gefunden")
        sheet = doc.sheet(cls)
        is_classteacher = _classteacher(sheet).casefold() == teacher.casefold()
        # Der Klassenlehrer darf alle Block-Spalten bearbeiten (auch ohne Kürzel).
        editable = {
            c["col"]: c
            for c in _editable_columns(sheet, teacher, include_empty=is_classteacher)
        }
        if not editable:
            raise HTTPException(status_code=403, detail="Keine Bearbeitungsrechte")

        # Alle Notenspalten (für Meta-Bearbeitung durch den Klassenlehrer).
        grade_cols = {c["col"]: c for c in _grade_columns(sheet, include_empty=True)}
        # Summenspalten: Schnitt (nur Anzeige) + Endnote (Klassenlehrer editierbar).
        summary = {c["col"]: c for c in _summary_columns(sheet)}
        endnote_cols = {k for k, v in summary.items() if v["role"] == "endnote"}
        # Name/Vorname: freier Text, nur durch den Klassenlehrer.
        name_cols = {settings.NAME_COL.upper(), settings.FIRSTNAME_COL.upper()}
        # Meta-Zeilen: Zeilennummer -> (key, label, kind)
        meta_by_row = {r: (key, label, kind) for r, key, label, kind in _meta_row_defs()}

        # 1) Validierung (alles-oder-nichts)
        for e in data.entries:
            col = e.col.upper()
            if settings.STUDENT_ROW_START <= e.row <= settings.STUDENT_ROW_END:
                if col in name_cols and is_classteacher:
                    continue  # Name/Vorname: freier Text, keine Notenprüfung
                if col in editable:
                    pass  # eigene Teilnoten-Spalte
                elif col in endnote_cols and is_classteacher:
                    pass  # Endnote – nur Klassenlehrer
                else:
                    raise HTTPException(
                        status_code=403,
                        detail=f"Spalte {e.col} darf von {teacher} nicht bearbeitet werden",
                    )
                err = _validate_grade(e.value)
                if err:
                    raise HTTPException(status_code=400, detail=err)
            elif e.row in meta_by_row:
                if not is_classteacher:
                    raise HTTPException(
                        status_code=403,
                        detail="Kopfzeilen darf nur der Klassenlehrer ändern",
                    )
                if col not in grade_cols:
                    raise HTTPException(
                        status_code=403, detail=f"Spalte {e.col} ist keine Notenspalte"
                    )
                if meta_by_row[e.row][2] == "number":
                    err = _validate_weight(e.value)
                    if err:
                        raise HTTPException(status_code=400, detail=err)
            else:
                raise HTTPException(status_code=400, detail=f"Zeile {e.row} unzulässig")

        # 2) Schreiben
        log_lines = []
        ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        name_c = col_to_index(settings.NAME_COL)
        vn_c = col_to_index(settings.FIRSTNAME_COL)
        for e in data.entries:
            row_idx = e.row - 1
            col_idx = col_to_index(e.col)
            s = e.value.strip()
            is_meta = e.row in meta_by_row
            is_number = is_meta and meta_by_row[e.row][2] == "number"
            is_name = e.col.upper() in name_cols and not is_meta

            if is_name:
                sheet.set_text(row_idx, col_idx, s)  # Name/Vorname: freier Text
            elif not is_meta and (s == "" or s in settings.GRADE_ALLOWED_TEXT):
                sheet.set_text(row_idx, col_idx, s)  # Note leeren / Platzhalter
            elif not is_meta:
                sheet.set_number(row_idx, col_idx, float(s.replace(",", ".")))
            elif is_number and s != "":
                sheet.set_number(row_idx, col_idx, float(s.replace(",", ".")))
            else:  # Meta-Text (Fach/Kürzel/Kommentar) oder leeres Gewicht
                sheet.set_text(row_idx, col_idx, s)

            col_meta = (
                grade_cols.get(e.col.upper())
                or summary.get(e.col.upper())
                or editable.get(e.col.upper())
            )
            fach = ""
            if col_meta:
                fach = " / ".join(p for p in (col_meta["block"], col_meta["label"]) if p)
            if is_meta:
                label = meta_by_row[e.row][1]
                log_lines.append(
                    f"{ts} | {teacher} | {cls} | [Kopf] {label} | "
                    f"{fach} ({e.col}) | {s or '(leer)'}"
                )
            elif is_name:
                feld = "Name" if e.col.upper() == settings.NAME_COL.upper() else "Vorname"
                log_lines.append(
                    f"{ts} | {teacher} | {cls} | [Schüler Zeile {e.row}] {feld} | "
                    f"({e.col}) | {s or '(leer)'}"
                )
            else:
                student = (
                    sheet.get_text(row_idx, name_c) + " " + sheet.get_text(row_idx, vn_c)
                ).strip() or f"Zeile {e.row}"
                log_lines.append(
                    f"{ts} | {teacher} | {cls} | {student} | "
                    f"{fach} ({e.col}) | {s or '(leer)'}"
                )

        # 3) Speichern + Protokoll
        doc.save()
        _write_log(log_lines)

    return {"status": "ok", "written": len(data.entries)}


def _write_log(lines: List[str]):
    if not lines:
        return
    try:
        with open(settings.LOG_PATH, "a", encoding="utf-8") as fh:
            for ln in lines:
                fh.write(ln + "\n")
    except OSError:
        pass  # Protokoll darf das Speichern der Noten nicht blockieren


def _as_str(v) -> str:
    if v == "" or v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


@app.get("/api/classes/{cls}/export")
def export_class(cls: str, teacher: str = Depends(current_teacher)):
    """Export der ausgewählten Klasse als eigenständige ODS (nur Klassenlehrer)."""
    doc = _open()
    if cls not in _class_sheets(doc):
        raise HTTPException(status_code=404, detail="Klasse nicht gefunden")
    sheet = doc.sheet(cls)
    if _classteacher(sheet).casefold() != teacher.casefold():
        raise HTTPException(
            status_code=403, detail="Nur der Klassenlehrer darf exportieren"
        )
    # Alle anderen Blätter (inkl. Login_Daten) entfernen -> nur diese Klasse.
    doc.remove_sheets_except(cls)
    data = doc.to_bytes()
    return Response(
        content=data,
        media_type="application/vnd.oasis.opendocument.spreadsheet",
        headers={"Content-Disposition": f'attachment; filename="{cls}.ods"'},
    )


@app.get("/api/health")
def health():
    return {"status": "ok"}
