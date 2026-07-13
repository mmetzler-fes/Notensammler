"""ETL: ODS-Quelldateien -> Datenbank -> Notenblatt-Spalten.

Ablauf (siehe implementationplan.md):
1. ``Vorlage_Klassen.ods``  -> Tabelle ``klassen``
2. ``Deputat.ods/Rohdaten`` -> Tabelle ``deputat`` (nur bekannte Klassen)
3. Gewichtung je Deputatszeile -> Tabelle ``notenblatt``
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

from .config import settings
from .db import Deputat, Klasse, Notenblatt, Noteneintrag
from .ods import OdsDocument, col_to_index
from .weights import Blockplan, KennungError, calculate_weight

HALBJAHRE = (1, 2)
GRUPPEN_PAAR = ("A", "B")


class ImportBlocked(RuntimeError):
    """Neuimport würde bereits eingegebene Noten verwerfen."""


@dataclass
class VerworfeneZeile:
    """Eine Rohdaten-Zeile, die nicht ins Deputat übernommen wurde."""

    zeile: int  # Zeilennummer in Deputat.ods/Rohdaten (1-basiert, wie LibreOffice)
    lehrer: str
    klasse: str
    gruppe: str
    fach: str
    kennung: str
    grund: str


@dataclass
class ImportReport:
    klassen: int = 0
    deputat: int = 0
    notenblatt: int = 0
    verworfen: list[VerworfeneZeile] = None
    warnungen: list[str] = None

    def __post_init__(self):
        if self.warnungen is None:
            self.warnungen = []
        if self.verworfen is None:
            self.verworfen = []


def parse_gruppe(wert) -> str:
    """'A', 'Gr. A', 'Gr.B' -> 'A'; leer -> '' (ganze Klasse)."""
    text = str(wert).strip()
    return re.sub(r"^Gr\.?\s*", "", text, flags=re.IGNORECASE).strip().upper()


def parse_stunden(wert) -> int:
    """Anzahl Unterrichtsstunden aus der Spalte "Stunde": '7-10' -> 4, '5' -> 1."""
    text = str(wert).strip()
    m = re.match(r"^(\d+)\s*-\s*(\d+)$", text)
    if m:
        return max(1, int(m.group(2)) - int(m.group(1)) + 1)
    return 1


# --- 1. Klassen --------------------------------------------------------------

def import_klassen(session, path: str | None = None) -> int:
    doc = OdsDocument(path or settings.KLASSEN_ODS)
    sheet = doc.sheet(settings.KLASSEN_SHEET)
    row = settings.KLASSEN_FIRST_ROW - 1

    anzahl = 0
    while True:
        klasse = str(sheet.get_value(row, 0)).strip()
        if not klasse:
            break
        session.add(
            Klasse(klasse=klasse, klassenlehrer=str(sheet.get_value(row, 1)).strip())
        )
        anzahl += 1
        row += 1
    session.flush()
    return anzahl


# --- 2. Blockplan + Deputat --------------------------------------------------

def load_blockplan(path: str | None = None) -> Blockplan:
    """Schulwochen und Blockwochen je Halbjahr aus dem Wechselplan."""
    doc = OdsDocument(path or settings.DEPUTAT_ODS)
    sheet = doc.sheet(settings.WECHSELPLAN_SHEET)
    c_woche = col_to_index(settings.WECHSELPLAN_WOCHE_COL)
    c_block = col_to_index(settings.WECHSELPLAN_BLOCK_COL)
    c_hj = col_to_index(settings.WECHSELPLAN_HJ_COL)
    hj_map = {
        settings.WECHSELPLAN_HJ1.upper(): 1,
        settings.WECHSELPLAN_HJ2.upper(): 2,
    }

    plan = Blockplan()
    wochen: dict[int, set] = defaultdict(set)
    leer = 0
    row = settings.WECHSELPLAN_FIRST_ROW - 1
    while leer < 20:
        hj = hj_map.get(str(sheet.get_value(row, c_hj)).strip().upper())
        woche = sheet.get_value(row, c_woche)
        block = str(sheet.get_value(row, c_block)).strip().upper()
        if hj is None and woche == "" and not block:
            leer += 1
            row += 1
            continue
        leer = 0
        if hj is not None:
            # Ferienwochen haben keine Schulwochen-Nummer und zählen nicht mit.
            if woche != "":
                wochen[hj].add(woche)
            if block:
                plan.bloecke[(block, hj)] = plan.bloecke.get((block, hj), 0) + 1
        row += 1

    plan.schulwochen = {hj: len(w) for hj, w in wochen.items()}
    return plan


def import_deputat(session, path: str | None = None) -> tuple[int, list[VerworfeneZeile]]:
    """Rohdaten importieren; Zeilen fremder Klassen/Fächer werden verworfen.

    Liefert die Zahl der übernommenen Zeilen und die verworfenen Zeilen mit Grund.
    """
    doc = OdsDocument(path or settings.DEPUTAT_ODS)
    sheet = doc.sheet(settings.ROHDATEN_SHEET)
    cols = {
        "stunde": col_to_index(settings.ROHDATEN_STUNDE_COL),
        "lehrer": col_to_index(settings.ROHDATEN_LEHRER_COL),
        "klasse": col_to_index(settings.ROHDATEN_KLASSE_COL),
        "gruppe": col_to_index(settings.ROHDATEN_GRUPPE_COL),
        "fach": col_to_index(settings.ROHDATEN_FACH_COL),
        "kennung": col_to_index(settings.ROHDATEN_KENNUNG_COL),
    }
    bekannte = {k.klasse for k in session.query(Klasse).all()}
    faecher = set(settings.BFK_FAECHER)

    uebernommen = 0
    verworfen: list[VerworfeneZeile] = []
    leer = 0
    row = settings.ROHDATEN_FIRST_ROW - 1
    while leer < 20:
        lehrer = str(sheet.get_value(row, cols["lehrer"])).strip()
        klasse = str(sheet.get_value(row, cols["klasse"])).strip()
        if not lehrer and not klasse:
            leer += 1
            row += 1
            continue
        leer = 0
        gruppe = parse_gruppe(sheet.get_value(row, cols["gruppe"]))
        fach = str(sheet.get_value(row, cols["fach"])).strip()
        kennung = str(sheet.get_value(row, cols["kennung"])).strip()

        gruende = []
        if klasse not in bekannte:
            gruende.append("Klasse nicht in Vorlage_Klassen")
        if fach not in faecher:
            gruende.append(f"Fach zählt nicht zur BFK-Note ({', '.join(settings.BFK_FAECHER)})")
        if gruende:
            verworfen.append(
                VerworfeneZeile(
                    zeile=row + 1, lehrer=lehrer, klasse=klasse, gruppe=gruppe,
                    fach=fach, kennung=kennung, grund=" + ".join(gruende),
                )
            )
            row += 1
            continue

        session.add(
            Deputat(
                lehrerkuerzel=lehrer,
                klasse=klasse,
                gruppe=gruppe,
                fach=fach,
                deputat=kennung,
                stunden=parse_stunden(sheet.get_value(row, cols["stunde"])),
            )
        )
        uebernommen += 1
        row += 1

    session.flush()
    return uebernommen, verworfen


# --- 3. Notenblatt -----------------------------------------------------------

def build_notenblatt(session, blockplan: Blockplan) -> tuple[int, list[str]]:
    """Erzeugt aus den Deputatszeilen die Notenblatt-Spalten je Klasse."""
    warnungen: list[str] = []

    # (Klasse, Lehrer, Fach, Gruppe) -> Gewichte je HJ + Stunden.
    # Das Gewicht einer Deputatszeile ist der Rhythmus-Anteil mal der Anzahl der
    # Unterrichtsstunden (Spalte "Stunde", z. B. "7-10" = 4 Stunden). Mehrfach
    # eingetragener Unterricht (verschiedene Tage) summiert sich auf.
    agg: dict[tuple, dict] = defaultdict(lambda: {"w": {1: 0.0, 2: 0.0}, "stunden": 0})
    for d in session.query(Deputat).all():
        try:
            w1, w2 = calculate_weight(d.deputat, blockplan)
        except KennungError as exc:
            warnungen.append(f"{d.klasse}/{d.lehrerkuerzel}/{d.fach}: {exc}")
            continue
        eintrag = agg[(d.klasse, d.lehrerkuerzel, d.fach, d.gruppe)]
        eintrag["w"][1] += w1 * d.stunden
        eintrag["w"][2] += w2 * d.stunden
        eintrag["stunden"] += d.stunden

    spalten = _merge_gruppen(agg)

    anzahl = 0
    for (klasse, lehrer, fach, gruppe), gewichte in sorted(spalten.items()):
        for hj in HALBJAHRE:
            if gewichte[hj] <= 0:
                continue
            session.add(
                Notenblatt(
                    kategorie="BFK",
                    klasse=klasse,
                    gruppe=gruppe,
                    halbjahr=hj,
                    lehrerkuerzel=lehrer,
                    fach=fach,
                    gewichtung=gewichte[hj],
                )
            )
            anzahl += 1

    anzahl += _build_sonderzeilen(session, spalten)
    session.flush()
    return anzahl, warnungen


def _merge_gruppen(agg: dict[tuple, dict]) -> dict[tuple, dict[int, float]]:
    """Gruppe A und B zusammenfassen, wenn ein Lehrer beide gleich stark unterrichtet.

    Gleiche Stundenzahl und gleiche Gewichtung in beiden Gruppen bedeutet: der
    Lehrer unterrichtet faktisch die ganze Klasse -> eine Spalte ohne
    Gruppenkennung. Sonst bleibt es bei getrennten Spalten je Gruppe.
    """
    spalten: dict[tuple, dict[int, float]] = {}
    erledigt: set[tuple] = set()

    for key, daten in agg.items():
        if key in erledigt:
            continue
        klasse, lehrer, fach, gruppe = key
        partner = None
        if gruppe in GRUPPEN_PAAR:
            andere = GRUPPEN_PAAR[1 - GRUPPEN_PAAR.index(gruppe)]
            partner = agg.get((klasse, lehrer, fach, andere))

        if partner is not None and _gleichwertig(daten, partner):
            spalten[(klasse, lehrer, fach, "")] = dict(daten["w"])
            erledigt.add(key)
            erledigt.add((klasse, lehrer, fach, GRUPPEN_PAAR[1 - GRUPPEN_PAAR.index(gruppe)]))
        else:
            spalten[key] = dict(daten["w"])
            erledigt.add(key)

    return spalten


def _gleichwertig(a: dict, b: dict, eps: float = 1e-9) -> bool:
    return a["stunden"] == b["stunden"] and all(
        abs(a["w"][hj] - b["w"][hj]) < eps for hj in HALBJAHRE
    )


def _build_sonderzeilen(session, spalten: dict[tuple, dict[int, float]]) -> int:
    """PK, Verhalten und Mitarbeit: je Lehrer ein Eintrag mit Gewicht 1.

    PK bekommt jeder Lehrer, der die Klasse im Schuljahr unterrichtet.
    Verhalten und Mitarbeit nur die Lehrer, die im jeweiligen Halbjahr
    tatsächlich unterrichtet haben.
    """
    # Klasse -> Halbjahr -> Lehrer
    aktiv: dict[str, dict[int, set]] = defaultdict(lambda: {1: set(), 2: set()})
    for (klasse, lehrer, _fach, _gruppe), gewichte in spalten.items():
        for hj in HALBJAHRE:
            if gewichte[hj] > 0:
                aktiv[klasse][hj].add(lehrer)

    anzahl = 0
    for klasse, je_hj in sorted(aktiv.items()):
        alle_lehrer = je_hj[1] | je_hj[2]
        for hj in HALBJAHRE:
            for kategorie, lehrerliste in (
                ("PK", alle_lehrer),
                ("Verhalten", je_hj[hj]),
                ("Mitarbeit", je_hj[hj]),
            ):
                for lehrer in sorted(lehrerliste):
                    session.add(
                        Notenblatt(
                            kategorie=kategorie,
                            klasse=klasse,
                            gruppe="",
                            halbjahr=hj,
                            lehrerkuerzel=lehrer,
                            fach=kategorie,
                            gewichtung=1.0,
                        )
                    )
                    anzahl += 1
    return anzahl


# --- Gesamtlauf --------------------------------------------------------------

def reset_stammdaten(session, force: bool = False) -> None:
    """Leert Notenblatt, Deputat und Klassen (in Abhängigkeitsreihenfolge).

    Der Import baut die Stammdaten komplett neu auf. Bereits eingegebene Noten
    hängen an den Notenblatt-Spalten und gingen dabei verloren – deshalb bricht
    der Import ab, sobald Noten existieren (``force`` löscht sie bewusst mit).
    """
    noten = session.query(Noteneintrag).count()
    if noten and not force:
        raise ImportBlocked(
            f"{noten} Noteneintrag/-einträge vorhanden. Ein Neuimport würde die "
            "Notenblatt-Spalten und damit die Noten löschen."
        )
    session.query(Noteneintrag).delete()
    session.query(Notenblatt).delete()
    session.query(Deputat).delete()
    session.query(Klasse).delete()
    session.flush()


def run_import(session, force: bool = False) -> ImportReport:
    reset_stammdaten(session, force)

    report = ImportReport()
    report.klassen = import_klassen(session)
    report.deputat, report.verworfen = import_deputat(session)
    blockplan = load_blockplan()
    report.notenblatt, report.warnungen = build_notenblatt(session, blockplan)
    session.commit()
    return report
