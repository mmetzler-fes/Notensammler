"""End-to-End-Test der API gegen das committete Sample.

Aufruf (aus dem Ordner ``backend``):

    pip install pytest httpx
    python -m pytest

Getestet wird gegen ``../Gesamtnotenliste.ods`` (das versionierte, anonymisierte
Sample – NICHT die veränderliche Datei unter data/). Es wird nur eine Kopie
bearbeitet; das Original bleibt unverändert.

Struktur des Samples:
  Blatt "E1ME1": Klassenlehrer (C3) = "xxx"; Spalte L gehört "xxx",
                 die übrigen Spalten gehören "x".
  Blatt "Login_Daten": x / xtest, xxx / xxxtest
"""
import os
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "Gesamtnotenliste.ods"

CLASS = "E1ME1"
CT, CT_PW = "xxx", "xxxtest"   # Klassenlehrer
TEACHER, TEACHER_PW = "x", "xtest"  # Fachlehrer
CT_ONLY_COL = "L"              # Spalte, die nur dem Klassenlehrer gehört


@pytest.fixture()
def client(tmp_path):
    ods = tmp_path / "test.ods"
    shutil.copy(TEMPLATE, ods)
    os.environ["ODS_PATH"] = str(ods)
    os.environ["LOG_PATH"] = str(tmp_path / "log.txt")
    os.environ["JWT_SECRET"] = "test-secret-fuer-pytest-mindestens-32b"
    # Config/App erst nach dem Setzen der Env laden.
    import importlib
    from app import config as cfg
    importlib.reload(cfg)
    from app import main
    importlib.reload(main)
    from fastapi.testclient import TestClient
    return TestClient(main.app)


def _auth(client, kuerzel, passwort):
    r = client.post("/api/login", json={"kuerzel": kuerzel, "passwort": passwort})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_login_falsch(client):
    assert client.post(
        "/api/login", json={"kuerzel": CT, "passwort": "falsch"}
    ).status_code == 401


def test_klassenlehrer_darf_alles_schreiben(client):
    h = _auth(client, CT, CT_PW)
    classes = client.get("/api/classes", headers=h).json()["classes"]
    assert any(c["class"] == CLASS and c["is_classteacher"] for c in classes)

    r = client.post(
        f"/api/classes/{CLASS}/grades",
        headers=h,
        json={"entries": [{"row": 9, "col": CT_ONLY_COL, "value": "2"},
                          {"row": 10, "col": CT_ONLY_COL, "value": "3,5"}]},
    )
    assert r.status_code == 200 and r.json()["written"] == 2

    grades = client.get(f"/api/classes/{CLASS}/students", headers=h).json()["grades"]
    assert grades["9"][CT_ONLY_COL] == "2"
    assert grades["10"][CT_ONLY_COL] == "3.5"


def test_fremde_spalte_verboten(client):
    # Fachlehrer "x" besitzt Spalte L nicht (die gehört dem Klassenlehrer).
    h = _auth(client, TEACHER, TEACHER_PW)
    r = client.post(
        f"/api/classes/{CLASS}/grades",
        headers=h,
        json={"entries": [{"row": 9, "col": CT_ONLY_COL, "value": "2"}]},
    )
    assert r.status_code == 403


def test_ungueltige_note(client):
    h = _auth(client, CT, CT_PW)
    r = client.post(
        f"/api/classes/{CLASS}/grades",
        headers=h,
        json={"entries": [{"row": 9, "col": CT_ONLY_COL, "value": "9"}]},
    )
    assert r.status_code == 400


def test_leere_namen_werden_ausgeblendet(client):
    """Standard: nur benannte Zeilen; mit all_columns sieht der KL alle Zeilen."""
    h = _auth(client, CT, CT_PW)
    default = client.get(f"/api/classes/{CLASS}/students", headers=h).json()
    full = client.get(
        f"/api/classes/{CLASS}/students?all_columns=1", headers=h
    ).json()
    assert all(s["name"].strip() for s in default["students"])
    assert len(full["students"]) >= len(default["students"])
