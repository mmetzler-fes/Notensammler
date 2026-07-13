"""Export: Notenblatt-Einträge aus der Datenbank -> ODS-Datei je Klasse.

Erzeugt aus ``Vorlage.ods`` zwei Varianten:

* ``<Klasse>_1HJ.ods``  – nur Einträge des 1. Halbjahrs.
* ``<Klasse>_Jahr.ods`` – 1. und 2. Halbjahr zusammengeführt. Unterrichtet ein
  Lehrer dasselbe Fach in beiden Halbjahren, werden die Gewichte addiert;
  unterrichtet er nur im 2. Halbjahr, bekommt er eine eigene Spalte.

Die Schülerdaten bleiben in dieser Ausbaustufe leer.
"""
from __future__ import annotations

import os
from collections import defaultdict

from .config import settings
from .db import Klasse, Notenblatt
from .ods import OdsDocument, col_to_index

# Zeilen der Vorlage (1-basiert wie in LibreOffice).
FACH_ROW = 4
LEHRER_ROW = 5
GEWICHT_ROW = 6
KLASSENLEHRER_CELL = "C3"

# Nur im BFK-Block steht das Fach in Zeile 4; PK/V/M sind in der Vorlage
# bereits beschriftet und werden nicht überschrieben.
FACH_BLOCK = "BFK"


class ExportError(RuntimeError):
    pass


def _cell(ref: str) -> tuple[int, int]:
    """'C3' -> (2, 2)."""
    buchstaben = "".join(c for c in ref if c.isalpha())
    ziffern = "".join(c for c in ref if c.isdigit())
    return int(ziffern) - 1, col_to_index(buchstaben)


def collect_columns(session, klasse: str, jahr: bool) -> dict[str, list[dict]]:
    """Notenblatt-Spalten je Kategorie, sortiert und exportfertig."""
    query = session.query(Notenblatt).filter(Notenblatt.klasse == klasse)
    if not jahr:
        query = query.filter(Notenblatt.halbjahr == 1)

    # Beim Jahres-Export fallen HJ1 und HJ2 derselben Lehrkraft in eine Spalte.
    zusammen: dict[tuple, float] = defaultdict(float)
    for eintrag in query.all():
        key = (eintrag.kategorie, eintrag.fach, eintrag.lehrerkuerzel, eintrag.gruppe)
        if eintrag.kategorie == FACH_BLOCK:
            zusammen[key] += eintrag.gewichtung
        else:
            # PK/Verhalten/Mitarbeit: ein Eintrag je Lehrer, Gewicht bleibt 1.
            zusammen[key] = eintrag.gewichtung

    spalten: dict[str, list[dict]] = defaultdict(list)
    for (kategorie, fach, lehrer, gruppe), gewicht in sorted(zusammen.items()):
        spalten[kategorie].append(
            {"fach": fach, "lehrer": lehrer, "gruppe": gruppe, "gewicht": gewicht}
        )
    return spalten


def fill_sheet(sheet, klasse: str, klassenlehrer: str, spalten: dict[str, list[dict]]) -> list[str]:
    warnungen: list[str] = []

    row, col = _cell(settings.KLASSE_CELL)
    sheet.set_text(row, col, klasse)
    row, col = _cell(KLASSENLEHRER_CELL)
    sheet.set_text(row, col, klassenlehrer)

    for kategorie, first_col, last_col in settings.NOTENBLOECKE:
        first, last = col_to_index(first_col), col_to_index(last_col)
        eintraege = spalten.get(kategorie, [])
        platz = last - first + 1
        if len(eintraege) > platz:
            warnungen.append(
                f"{klasse}: {len(eintraege)} {kategorie}-Spalten, aber nur {platz} in der Vorlage"
            )
            eintraege = eintraege[:platz]

        for i, e in enumerate(eintraege):
            col = first + i
            if kategorie == FACH_BLOCK:
                fach = e["fach"]
                if e["gruppe"]:
                    fach = f"{fach} Gr.{e['gruppe']}"
                sheet.set_text(FACH_ROW - 1, col, fach)
            sheet.set_text(LEHRER_ROW - 1, col, e["lehrer"])
            sheet.set_number(GEWICHT_ROW - 1, col, e["gewicht"])

    return warnungen


def export_klasse(session, klasse: str, jahr: bool, ziel_dir: str | None = None) -> tuple[str, list[str]]:
    """Schreibt <Klasse>_1HJ.ods bzw. <Klasse>_Jahr.ods und liefert den Pfad."""
    eintrag = session.get(Klasse, klasse)
    if eintrag is None:
        raise ExportError(f"Unbekannte Klasse: {klasse}")

    blatt = settings.VORLAGE_SHEET_JAHR if jahr else settings.VORLAGE_SHEET_HJ1
    doc = OdsDocument(settings.VORLAGE_ODS)
    warnungen = fill_sheet(
        doc.sheet(blatt), klasse, eintrag.klassenlehrer, collect_columns(session, klasse, jahr)
    )
    doc.remove_sheets_except(blatt)

    ziel_dir = ziel_dir or settings.EXPORT_DIR
    os.makedirs(ziel_dir, exist_ok=True)
    pfad = os.path.join(ziel_dir, f"{klasse}_{'Jahr' if jahr else '1HJ'}.ods")
    doc.save(pfad)
    return pfad, warnungen


def export_alle(session, ziel_dir: str | None = None) -> tuple[list[str], list[str]]:
    """Exportiert für jede Klasse beide Varianten."""
    pfade: list[str] = []
    warnungen: list[str] = []
    for klasse in session.query(Klasse).order_by(Klasse.klasse).all():
        for jahr in (False, True):
            pfad, warn = export_klasse(session, klasse.klasse, jahr, ziel_dir)
            pfade.append(pfad)
            warnungen.extend(warn)
    return pfade, warnungen
