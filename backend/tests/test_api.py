"""End-to-End-Test der API gegen eine Kopie der ODS-Vorlage.

Aufruf (aus dem Ordner ``backend``):

    pip install pytest httpx
    python -m pytest

Die Testdatei wird automatisch aus ../data/Gesamtnotenliste.ods kopiert; die
Original-Datei wird nicht verändert.
"""
import os
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "data" / "Gesamtnotenliste.ods"


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
        "/api/login", json={"kuerzel": "MEM", "passwort": "x"}
    ).status_code == 401


def test_klassenlehrer_darf_alles_schreiben(client):
    h = _auth(client, "MEM", "test123")
    classes = client.get("/api/classes", headers=h).json()["classes"]
    assert any(c["class"] == "E2EG2" and c["is_classteacher"] for c in classes)

    r = client.post(
        "/api/classes/E2EG2/grades",
        headers=h,
        json={"entries": [{"row": 9, "col": "L", "value": "2"},
                          {"row": 10, "col": "L", "value": "3,5"}]},
    )
    assert r.status_code == 200 and r.json()["written"] == 2

    grades = client.get("/api/classes/E2EG2/students", headers=h).json()["grades"]
    assert grades["9"]["L"] == "2"
    assert grades["10"]["L"] == "3.5"


def test_fremde_spalte_verboten(client):
    h = _auth(client, "DIN", "k12h")  # DIN besitzt nur Spalte N in E2EG2
    r = client.post(
        "/api/classes/E2EG2/grades",
        headers=h,
        json={"entries": [{"row": 9, "col": "L", "value": "2"}]},
    )
    assert r.status_code == 403


def test_ungueltige_note(client):
    h = _auth(client, "MEM", "test123")
    r = client.post(
        "/api/classes/E2EG2/grades",
        headers=h,
        json={"entries": [{"row": 9, "col": "L", "value": "9"}]},
    )
    assert r.status_code == 400
