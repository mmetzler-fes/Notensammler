"""Zentrale, per Umgebungsvariablen überschreibbare Konfiguration.

Alle Zeilen-/Spaltengrenzen entsprechen dem Aufbau der Vorlage
``Gesamtnotenliste.ods`` und sind laut Designplan bewusst einstellbar.
Zeilen werden 1-basiert angegeben (wie in LibreOffice), Spalten als
Buchstaben (A, B, C, ...).
"""
from __future__ import annotations

import os


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


class Settings:
    # --- Datei / Ablage ---------------------------------------------------
    # Pfad zur ODS-Datei. Im Docker-Container wird das Verzeichnis /data als
    # Volume gemountet; lokal kann ODS_PATH auf die Datei im Repo zeigen.
    ODS_PATH: str = os.getenv("ODS_PATH", "/data/Gesamtnotenliste.ods")
    LOG_PATH: str = os.getenv("LOG_PATH", "/data/log_protokoll.txt")

    # --- Datenbank --------------------------------------------------------
    # SQLite genügt für den Schulbetrieb; für PostgreSQL nur die URL tauschen.
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///data/notensammler.db")

    # --- Quelldateien für den Import (ETL) --------------------------------
    KLASSEN_ODS: str = os.getenv("KLASSEN_ODS", "data/Vorlage_Klassen.ods")
    DEPUTAT_ODS: str = os.getenv("DEPUTAT_ODS", "data/Deputat.ods")
    VORLAGE_ODS: str = os.getenv("VORLAGE_ODS", "data/Vorlage.ods")
    EXPORT_DIR: str = os.getenv("EXPORT_DIR", "data/export")

    # Blatt "Klassen" (Vorlage_Klassen.ods): ab Zeile 2, Klasse / Klassenlehrer.
    KLASSEN_SHEET: str = os.getenv("KLASSEN_SHEET", "Klassen")
    KLASSEN_FIRST_ROW: int = _int("KLASSEN_FIRST_ROW", 2)

    # Blatt "Rohdaten" (Deputat.ods): ab Zeile 5.
    ROHDATEN_SHEET: str = os.getenv("ROHDATEN_SHEET", "Rohdaten")
    ROHDATEN_FIRST_ROW: int = _int("ROHDATEN_FIRST_ROW", 5)
    ROHDATEN_STUNDE_COL: str = os.getenv("ROHDATEN_STUNDE_COL", "B")
    ROHDATEN_LEHRER_COL: str = os.getenv("ROHDATEN_LEHRER_COL", "C")
    ROHDATEN_KLASSE_COL: str = os.getenv("ROHDATEN_KLASSE_COL", "F")
    ROHDATEN_GRUPPE_COL: str = os.getenv("ROHDATEN_GRUPPE_COL", "G")
    ROHDATEN_FACH_COL: str = os.getenv("ROHDATEN_FACH_COL", "H")
    ROHDATEN_KENNUNG_COL: str = os.getenv("ROHDATEN_KENNUNG_COL", "J")

    # Blatt "Wechselplan" (Deputat.ods): Schulwochen und Blockunterricht.
    WECHSELPLAN_SHEET: str = os.getenv("WECHSELPLAN_SHEET", "Wechselplan")
    WECHSELPLAN_FIRST_ROW: int = _int("WECHSELPLAN_FIRST_ROW", 4)
    WECHSELPLAN_WOCHE_COL: str = os.getenv("WECHSELPLAN_WOCHE_COL", "B")
    WECHSELPLAN_BLOCK_COL: str = os.getenv("WECHSELPLAN_BLOCK_COL", "M")
    WECHSELPLAN_HJ_COL: str = os.getenv("WECHSELPLAN_HJ_COL", "O")
    # Werte der Halbjahres-Spalte: "A" = 1. Halbjahr, "B" = 2. Halbjahr.
    WECHSELPLAN_HJ1: str = os.getenv("WECHSELPLAN_HJ1", "A")
    WECHSELPLAN_HJ2: str = os.getenv("WECHSELPLAN_HJ2", "B")

    # Fächer, die in die BFK-Note eingehen.
    BFK_FAECHER = [
        f.strip() for f in os.getenv("BFK_FAECHER", "BT,BT-L,BT-W").split(",") if f.strip()
    ]

    # --- Aufbau der Vorlage (Vorlage.ods) ---------------------------------
    VORLAGE_SHEET_HJ1: str = os.getenv("VORLAGE_SHEET_HJ1", "1HJ")
    VORLAGE_SHEET_JAHR: str = os.getenv("VORLAGE_SHEET_JAHR", "Jahr")
    KLASSE_CELL: str = os.getenv("KLASSE_CELL", "C1")

    # Notenspalten-Blöcke der Vorlage: "Kategorie:ErsteSpalte:LetzteSpalte".
    # Die Fach-Zeile ist außerhalb von BFK bereits in der Vorlage beschriftet
    # (PK/V/M) und wird beim Export nicht überschrieben.
    NOTENBLOECKE = [
        tuple(p.split(":"))
        for p in os.getenv(
            "NOTENBLOECKE", "BFK:E:R,PK:V:AF,Verhalten:AJ:AT,Mitarbeit:AX:BH"
        ).split(",")
        if p.count(":") == 2
    ]

    # Blattname mit den Login-Daten (nicht als Klasse behandelt).
    LOGIN_SHEET: str = os.getenv("LOGIN_SHEET", "Login_Daten")
    # Erste Datenzeile im Login-Blatt (1-basiert) sowie Spalten.
    LOGIN_FIRST_ROW: int = _int("LOGIN_FIRST_ROW", 3)
    LOGIN_KUERZEL_COL: str = os.getenv("LOGIN_KUERZEL_COL", "A")
    LOGIN_PASSWORT_COL: str = os.getenv("LOGIN_PASSWORT_COL", "B")

    # --- Aufbau der Klassenblätter ---------------------------------------
    CLASSTEACHER_CELL: str = os.getenv("CLASSTEACHER_CELL", "C3")  # Klassenlehrer-Kürzel
    BLOCK_ROW: int = _int("BLOCK_ROW", 3)       # Blocktitel (z. B. "BFK- Teilnoten")
    SUBJECT_ROW: int = _int("SUBJECT_ROW", 4)   # Fach-Bezeichnungen
    TEACHER_ROW: int = _int("TEACHER_ROW", 5)   # freigeschaltetes Lehrerkürzel je Spalte
    WEIGHT_ROW: int = _int("WEIGHT_ROW", 6)     # Gewichtung
    COMMENT_ROW: int = _int("COMMENT_ROW", 8)   # Kommentar/Header je Spalte (z. B. "1.HJ")
    STUDENT_ROW_START: int = _int("STUDENT_ROW_START", 9)
    STUDENT_ROW_END: int = _int("STUDENT_ROW_END", 40)
    AVERAGE_ROW: int = _int("AVERAGE_ROW", 41)  # Spaltenmittel ("Durchschnitt")

    NR_COL: str = os.getenv("NR_COL", "A")
    NAME_COL: str = os.getenv("NAME_COL", "B")
    FIRSTNAME_COL: str = os.getenv("FIRSTNAME_COL", "C")

    # Summenspalten je Block: "Schnitt:Endnote"-Paare (Komma-getrennt).
    # Schnitt wird nur angezeigt (Formel), Endnote darf der Klassenlehrer setzen.
    # Reihenfolge: BFK, PK, Verhalten, Mitarbeit.
    SUMMARY_COLUMNS = [
        tuple(p.split(":"))
        for p in os.getenv("SUMMARY_COLUMNS", "Y:Z,AM:AN,BA:BB,BO:BP").split(",")
        if ":" in p
    ]

    # Bis zu welcher Spalte (Index, 0-basiert) nach Notenspalten gesucht wird.
    MAX_COL_INDEX: int = _int("MAX_COL_INDEX", 80)

    # --- Notenvalidierung -------------------------------------------------
    GRADE_MIN: float = float(os.getenv("GRADE_MIN", "1"))
    GRADE_MAX: float = float(os.getenv("GRADE_MAX", "6"))
    # Zusätzlich erlaubte Text-Eingaben (z. B. Platzhalter für "keine Note").
    GRADE_ALLOWED_TEXT = set(
        s.strip() for s in os.getenv("GRADE_ALLOWED_TEXT", "-").split(",") if s.strip()
    )

    # --- Auth -------------------------------------------------------------
    JWT_SECRET: str = os.getenv("JWT_SECRET", "bitte-in-produktion-aendern")
    JWT_ALGORITHM: str = "HS256"
    JWT_TTL_MINUTES: int = _int("JWT_TTL_MINUTES", 120)

    # CORS: erlaubte Frontend-Origins (Komma-getrennt) oder "*".
    CORS_ORIGINS = [
        o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()
    ]


settings = Settings()
