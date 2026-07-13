"""End-to-End: Beispieldateien -> Datenbank -> Notenblatt -> ODS.

Aufruf (aus dem Ordner ``backend``):

    python -m pytest tests/test_etl_export.py
"""
from pathlib import Path

import pytest

from app.config import settings
from app.db import Notenblatt, init_db, make_engine, make_session_factory
from app.etl import run_import
from app.export import export_klasse
from app.ods import OdsDocument, col_to_index

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
QUELLEN = [DATA / n for n in ("Vorlage_Klassen.ods", "Deputat.ods", "Vorlage.ods")]

BLO1_HJ1, BLO1_HJ2 = 5 / 19, 6 / 19
BLO3_HJ1, BLO3_HJ2 = 5 / 19, 7 / 19

# data/ ist nicht versioniert (echte Personendaten); ohne Quelldateien kein Lauf.
pytestmark = pytest.mark.skipif(
    not all(p.exists() for p in QUELLEN),
    reason="Beispieldateien unter data/ nicht vorhanden",
)


@pytest.fixture
def session(monkeypatch):
    monkeypatch.setattr(settings, "KLASSEN_ODS", str(DATA / "Vorlage_Klassen.ods"))
    monkeypatch.setattr(settings, "DEPUTAT_ODS", str(DATA / "Deputat.ods"))
    monkeypatch.setattr(settings, "VORLAGE_ODS", str(DATA / "Vorlage.ods"))

    engine = make_engine("sqlite://")  # nur im Speicher
    init_db(engine)
    with make_session_factory(engine)() as s:
        run_import(s)
        yield s


def spalten(session, klasse, kategorie="BFK", hj=None):
    """{(fach, gruppe, lehrer): gewicht}"""
    q = session.query(Notenblatt).filter_by(klasse=klasse, kategorie=kategorie)
    if hj is not None:
        q = q.filter_by(halbjahr=hj)
    return {(e.fach, e.gruppe, e.lehrerkuerzel): e.gewichtung for e in q.all()}


def test_import_verwirft_fremde_klassen_und_faecher(session):
    from app.db import Deputat, Klasse

    klassen = {k.klasse for k in session.query(Klasse).all()}
    assert klassen == {"E1BT2", "E1ME2", "E2BT2", "E2EG2", "E3BT2", "E3ME1", "E3ME2"}

    for d in session.query(Deputat).all():
        assert d.klasse in klassen
        assert d.fach in settings.BFK_FAECHER


def test_gruppe_wird_normalisiert():
    from app.etl import parse_gruppe

    assert parse_gruppe("A") == "A"
    assert parse_gruppe("Gr. B") == "B"
    assert parse_gruppe("Gr.a") == "A"
    assert parse_gruppe("") == ""


def test_verworfene_zeilen_werden_mit_grund_gemeldet(session):
    from app.etl import import_deputat

    _uebernommen, verworfen = import_deputat(session)
    gruende = {(v.klasse, v.fach): v.grund for v in verworfen}

    # Fremde Klasse, aber BFK-Fach.
    assert "Klasse nicht in Vorlage_Klassen" in gruende[("E4BT2", "BT-L")]
    # Bekanntes Fach-Kriterium greift unabhängig von der Klasse.
    assert "BFK" in gruende[("TG12/2", "IT")]
    assert all(v.zeile > 0 for v in verworfen)


def test_erneuter_import_ist_wiederholbar(session):
    from app.db import Klasse

    vorher = spalten(session, "E3BT2", hj=1)
    run_import(session)  # zweiter Lauf auf gefüllter Datenbank
    assert session.query(Klasse).count() == 7
    assert spalten(session, "E3BT2", hj=1) == vorher


def test_import_schuetzt_vorhandene_noten(session):
    from app.db import Noteneintrag, Schueler
    from app.etl import ImportBlocked

    schueler = Schueler(name="Muster", vorname="Max", klasse="E3BT2")
    session.add(schueler)
    session.flush()
    spalte = session.query(Notenblatt).filter_by(klasse="E3BT2").first()
    session.add(
        Noteneintrag(schuelerid=schueler.schuelerid, notenblatt_id=spalte.eintrag,
                     lehrer=spalte.lehrerkuerzel, note=2.0)
    )
    session.flush()

    with pytest.raises(ImportBlocked):
        run_import(session)

    session.rollback()


def test_blockunterricht_gewichtung(session):
    # MUS unterrichtet E2BT2/BT als BLO2 (6 Blockwochen je Halbjahr, 19 Schulwochen).
    assert spalten(session, "E2BT2", hj=1)[("BT", "", "MUS")] == pytest.approx(2 * 6 / 19)
    assert spalten(session, "E2BT2", hj=2)[("BT", "", "MUS")] == pytest.approx(2 * 6 / 19)

    # MEM unterrichtet E3BT2/BT-L Gr.B als BLO3 -> im 2. HJ mehr Blockwochen.
    assert spalten(session, "E3BT2", hj=1)[("BT-L", "B", "MEM")] == pytest.approx(4 * BLO3_HJ1)
    assert spalten(session, "E3BT2", hj=2)[("BT-L", "B", "MEM")] == pytest.approx(4 * BLO3_HJ2)


def test_mehrfacher_unterricht_summiert_gewichte(session):
    # MUS unterrichtet E3BT2/BT in drei Stundenplan-Zeilen mit BLO3.
    assert spalten(session, "E3BT2", hj=1)[("BT", "", "MUS")] == pytest.approx(3 * 2 * BLO3_HJ1)
    assert spalten(session, "E3BT2", hj=2)[("BT", "", "MUS")] == pytest.approx(3 * 2 * BLO3_HJ2)


def test_ganzjahres_kennung_ohne_praefix(session):
    # MEM unterrichtet E2EG2/BT mit Kennung "21" -> jede 2. Woche, ganzes Jahr.
    assert spalten(session, "E2EG2", hj=1)[("BT", "", "MEM")] == pytest.approx(4 * 0.5)
    assert spalten(session, "E2EG2", hj=2)[("BT", "", "MEM")] == pytest.approx(4 * 0.5)


def test_stundenzahl_geht_ins_gewicht_ein(session):
    from app.db import Deputat
    from app.etl import parse_stunden

    assert parse_stunden("7-10") == 4  # 7. bis 10. Stunde
    assert parse_stunden("1-4") == 4
    assert parse_stunden("5") == 1
    assert parse_stunden("") == 1

    # MEM unterrichtet E2EG2/BT in der 7.-10. Stunde (4h) mit Kennung "21"
    # -> Rhythmus 0.5 mal 4 Stunden = 2.0 je Halbjahr.
    zeile = (
        session.query(Deputat)
        .filter_by(klasse="E2EG2", lehrerkuerzel="MEM", fach="BT")
        .one()
    )
    assert zeile.stunden == 4
    assert spalten(session, "E2EG2", hj=1)[("BT", "", "MEM")] == pytest.approx(2.0)


def test_beide_gruppen_gleich_stark_ergeben_eine_spalte(session):
    # MEM unterrichtet E1ME2/BT-L in Gr.A und Gr.B (je "B22", gleiche Stundenzahl)
    # -> eine Spalte ohne Gruppenkennung, nur im 2. Halbjahr.
    hj2 = spalten(session, "E1ME2", hj=2)
    assert hj2[("BT-L", "", "MEM")] == pytest.approx(2 * 0.5)
    assert ("BT-L", "A", "MEM") not in hj2
    assert ("BT-L", "B", "MEM") not in hj2
    # MUS unterrichtet dort nur Gr.B -> Gruppenkennung bleibt erhalten.
    assert hj2[("BT-L", "B", "MUS")] == pytest.approx(2 * BLO1_HJ2)


def test_praefix_b_erscheint_nicht_im_ersten_halbjahr(session):
    assert ("BT-L", "", "MEM") not in spalten(session, "E1ME2", hj=1)
    assert spalten(session, "E3ME1", hj=1) == {}


def test_sonderzeilen_pk_verhalten_mitarbeit(session):
    # PK: jeder Lehrer der Klasse im Schuljahr - auch wer nur im 2. HJ unterrichtet.
    pk = spalten(session, "E1ME2", "PK", hj=1)
    assert {lehrer for _f, _g, lehrer in pk} == {"MEM", "MUS"}
    assert set(pk.values()) == {1.0}

    # Verhalten/Mitarbeit: nur wer im jeweiligen Halbjahr unterrichtet hat.
    for kategorie in ("Verhalten", "Mitarbeit"):
        hj1 = spalten(session, "E1ME2", kategorie, hj=1)
        hj2 = spalten(session, "E1ME2", kategorie, hj=2)
        assert {lehrer for _f, _g, lehrer in hj1} == {"MUS"}
        assert {lehrer for _f, _g, lehrer in hj2} == {"MEM", "MUS"}


# --- Export ------------------------------------------------------------------

def _lies(pfad, blatt):
    """{Spaltenbuchstabe: (Fach, Lehrer, Gewicht)} des BFK-Blocks E..R."""
    doc = OdsDocument(pfad)
    assert doc.sheet_names() == [blatt]
    sheet = doc.sheet(blatt)
    spalten = {}
    for c in range(col_to_index("E"), col_to_index("R") + 1):
        lehrer = sheet.get_value(4, c)
        if lehrer == "":
            continue
        spalten[c] = (sheet.get_value(3, c), lehrer, float(sheet.get_value(5, c)))
    return sheet, spalten


def test_export_1hj_enthaelt_nur_erstes_halbjahr(session, tmp_path):
    pfad, warnungen = export_klasse(session, "E3BT2", jahr=False, ziel_dir=str(tmp_path))
    assert warnungen == []
    assert pfad.endswith("E3BT2_1HJ.ods")

    sheet, bfk = _lies(pfad, "1HJ")
    assert sheet.get_value(0, col_to_index("D")) == "E3BT2"
    assert sheet.get_value(2, col_to_index("C")) == "MUS"  # Klassenlehrer

    werte = {(f, l): g for f, l, g in bfk.values()}
    assert werte[("BT", "MUS")] == pytest.approx(3 * 2 * BLO3_HJ1)
    assert werte[("BT-L Gr.B", "MEM")] == pytest.approx(4 * BLO3_HJ1)


def test_export_jahr_addiert_beide_halbjahre(session, tmp_path):
    pfad, _ = export_klasse(session, "E3BT2", jahr=True, ziel_dir=str(tmp_path))
    _sheet, bfk = _lies(pfad, "Jahr")

    werte = {(f, l): g for f, l, g in bfk.values()}
    assert werte[("BT", "MUS")] == pytest.approx(3 * 2 * (BLO3_HJ1 + BLO3_HJ2))
    assert werte[("BT-L Gr.B", "MEM")] == pytest.approx(4 * (BLO3_HJ1 + BLO3_HJ2))


def test_export_jahr_gibt_reinen_zweit_halbjahres_lehrer_eigene_spalte(session, tmp_path):
    pfad, _ = export_klasse(session, "E1ME2", jahr=True, ziel_dir=str(tmp_path))
    _sheet, bfk = _lies(pfad, "Jahr")

    werte = {(f, l): g for f, l, g in bfk.values()}
    # MEM unterrichtet nur im 2. HJ -> eigene Spalte mit seiner Gewichtung.
    assert werte[("BT-L", "MEM")] == pytest.approx(2 * 0.5)
    # MUS unterrichtet Gr.B in beiden Halbjahren -> addiert.
    assert werte[("BT-L Gr.B", "MUS")] == pytest.approx(2 * (BLO1_HJ1 + BLO1_HJ2))


def test_export_spalten_werden_von_links_gefuellt(session, tmp_path):
    pfad, _ = export_klasse(session, "E3BT2", jahr=False, ziel_dir=str(tmp_path))
    _sheet, bfk = _lies(pfad, "1HJ")
    erste = col_to_index("E")
    assert sorted(bfk) == list(range(erste, erste + len(bfk)))
