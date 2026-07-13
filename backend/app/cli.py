"""CLI für Import und Export (Testlauf ohne Web-Oberfläche).

    python -m app.cli import              Quelldateien -> Datenbank
    python -m app.cli export              alle Klassen -> data/export/*.ods
    python -m app.cli export --klasse E1BT2
    python -m app.cli show                Notenblatt-Spalten anzeigen
"""
from __future__ import annotations

import argparse
import sys

from .config import settings
from .db import Notenblatt, init_db, make_engine, make_session_factory
from .etl import run_import
from .export import export_alle, export_klasse


def _session():
    engine = make_engine()
    init_db(engine)
    return make_session_factory(engine)()


def cmd_import(_args) -> int:
    session = _session()
    report = run_import(session)
    print(f"Klassen:    {report.klassen}")
    print(f"Deputat:    {report.deputat} übernommen, {report.verworfen} verworfen")
    print(f"Notenblatt: {report.notenblatt} Spalten")
    for w in report.warnungen:
        print(f"  WARNUNG: {w}", file=sys.stderr)
    return 0


def cmd_export(args) -> int:
    session = _session()
    if args.klasse:
        pfade = []
        warnungen = []
        for jahr in (False, True):
            pfad, warn = export_klasse(session, args.klasse, jahr, args.out)
            pfade.append(pfad)
            warnungen.extend(warn)
    else:
        pfade, warnungen = export_alle(session, args.out)

    for p in pfade:
        print(p)
    for w in warnungen:
        print(f"  WARNUNG: {w}", file=sys.stderr)
    return 0


def cmd_show(args) -> int:
    session = _session()
    query = session.query(Notenblatt).order_by(
        Notenblatt.klasse, Notenblatt.kategorie, Notenblatt.halbjahr,
        Notenblatt.fach, Notenblatt.lehrerkuerzel,
    )
    if args.klasse:
        query = query.filter(Notenblatt.klasse == args.klasse)
    if args.kategorie:
        query = query.filter(Notenblatt.kategorie == args.kategorie)

    aktuelle = None
    for e in query.all():
        kopf = (e.klasse, e.kategorie, e.halbjahr)
        if kopf != aktuelle:
            print(f"\n{e.klasse}  {e.kategorie}  {e.halbjahr}. HJ")
            aktuelle = kopf
        gruppe = f" Gr.{e.gruppe}" if e.gruppe else ""
        print(f"  {e.fach + gruppe:<12} {e.lehrerkuerzel:<5} {e.gewichtung:.4f}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="notensammler")
    parser.add_argument("--db", help=f"DATABASE_URL (Standard: {settings.DATABASE_URL})")
    sub = parser.add_subparsers(dest="befehl", required=True)

    sub.add_parser("import", help="Quelldateien in die Datenbank importieren")

    p_export = sub.add_parser("export", help="Notenblätter als ODS exportieren")
    p_export.add_argument("--klasse", help="nur diese Klasse")
    p_export.add_argument("--out", help=f"Zielverzeichnis (Standard: {settings.EXPORT_DIR})")

    p_show = sub.add_parser("show", help="Notenblatt-Spalten anzeigen")
    p_show.add_argument("--klasse")
    p_show.add_argument("--kategorie")

    args = parser.parse_args(argv)
    if args.db:
        settings.DATABASE_URL = args.db

    return {"import": cmd_import, "export": cmd_export, "show": cmd_show}[args.befehl](args)


if __name__ == "__main__":
    raise SystemExit(main())
