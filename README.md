# Notensammler

Web-Anwendung, mit der Lehrkräfte über ein Browser-Frontend Noten in die
LibreOffice-Datei **`Gesamtnotenliste.ods`** eintragen. Umsetzung des
[Designplans](designplan.md).

```
[ Browser ] → React/Nginx (Container) → FastAPI (Container) → Gesamtnotenliste.ods (Volume)
                                                            → log_protokoll.txt
```

## Aufbau der ODS-Datei

Jedes **Klassenblatt** (Blattname = Klasse, z. B. `E2EG2`) folgt diesem Schema
(alle Grenzen sind in [`backend/app/config.py`](backend/app/config.py) per
Umgebungsvariable einstellbar):

| Ort | Bedeutung |
|-----|-----------|
| `C3` | Klassenlehrer-Kürzel – darf **alle** Notenspalten bearbeiten |
| Zeile 4 | Fach-Bezeichnungen (Anzeige-Label je Spalte) |
| Zeile 5 | Lehrerkürzel je Spalte → **diese** Spalte ist für dieses Kürzel freigeschaltet |
| Zeile 6 | Gewichtung |
| Zeilen 9–40 | Schüler: `A`=Nr, `B`=Name, `C`=Vorname, restliche Spalten = Noten |

Das Blatt **`Login_Daten`** enthält ab Zeile 3: `A`=Kürzel, `B`=Passwort.
Passwörter dürfen Klartext **oder** bcrypt-Hashes (`$2b$…`) sein – das Backend
erkennt beides automatisch.

## Schnellstart mit Docker

```bash
# ODS-Datei liegt bereits unter ./data/Gesamtnotenliste.ods
export JWT_SECRET="$(openssl rand -hex 32)"   # unbedingt setzen!
docker compose up --build
```

Frontend danach auf <http://localhost:8080>. Beispiel-Login aus der Vorlage:
`MEM` / `test123` (Klassenlehrer von `E2EG2`).

Die ODS-Datei und `log_protokoll.txt` liegen im Host-Ordner `./data` und
überleben Container-Neustarts.

## Lokale Entwicklung (ohne Docker)

Backend:

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export ODS_PATH="$PWD/../data/Gesamtnotenliste.ods"
export LOG_PATH="$PWD/../data/log_protokoll.txt"
export JWT_SECRET="dev-secret-bitte-aendern"
uvicorn app.main:app --reload
```

Frontend (Proxy leitet `/api` an `localhost:8000`):

```bash
cd frontend
npm install
npm run dev   # http://localhost:5173
```

## API

| Methode | Pfad | Zweck |
|---------|------|-------|
| `POST` | `/api/login` | `{kuerzel, passwort}` → `{token}` (JWT) |
| `GET` | `/api/classes` | Klassen mit Bearbeitungsrechten des Lehrers |
| `GET` | `/api/classes/{cls}/students` | Schüler + editierbare Spalten + aktuelle Werte |
| `POST` | `/api/classes/{cls}/grades` | Noten schreiben `{entries:[{row,col,value}]}` |

Alle Endpunkte außer `/api/login` erwarten den Header
`Authorization: Bearer <token>`.

## Sicherheits- und Betriebshinweise

- **Gleichzeitige Zugriffe:** Alle Schreibvorgänge sind im Backend per
  `asyncio.Lock` serialisiert; vor jedem Schreiben wird die Datei frisch
  geladen. Das Backend läuft daher bewusst mit **einem** Worker.
- **Datei-Integrität:** Gespeichert wird atomar (Schreiben in `.tmp`, dann
  `move`). Formeln, Formatierung und nicht angefasste Zellen bleiben erhalten.
- **HTTPS:** In Produktion **zwingend** hinter einen Reverse-Proxy (Traefik /
  Nginx Proxy Manager) mit TLS stellen – Passwörter nie über HTTP.
- **`JWT_SECRET`:** In Produktion ein langes Zufalls-Secret setzen.
- **Passwörter:** Für den Echtbetrieb die Klartext-Passwörter im Blatt
  `Login_Daten` durch bcrypt-Hashes ersetzen.
- **Protokoll:** Jeder erfolgreiche Speichervorgang wird zeilenweise in
  `log_protokoll.txt` geschrieben:
  `Zeitstempel | Kürzel | Klasse | Schüler | Fach (Spalte) | Note`.

## Tests

Ein End-to-End-Test der API (Login, Rechteprüfung, Schreiben, Protokoll) gegen
eine Kopie der ODS:

```bash
cd backend
ODS_PATH=/pfad/zu/kopie.ods LOG_PATH=/tmp/log.txt JWT_SECRET=test \
  python -m pytest   # bzw. das Skript in README-Historie
```
