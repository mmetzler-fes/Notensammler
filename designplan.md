[ Webbrowser (Lehrer) ] 
       │ (HTTPS / REST)
       ▼
[ React Frontend (Docker Container 1) ]
       │
       ▼
[ Python FastAPI Backend (Docker Container 2) ]
       │
       ├──► Liest/Schreibt: Noten.ods (Gemountetes Volume)
       └──► Schreibt: log_protokoll.txt
📋 Der Implementationsplan
Phase 1: Datenstruktur in der .ods-Datei vorbereiten
Bevor Code geschrieben wird, muss die LibreOffice-Datei klar strukturiert sein.

Blatt 1 ("Klassennamen"): z.B. Die Zeilen 9 bis 40 enthalten in Spalte A/B die Namen. Alle Spalten enthalten in Zeile 5 das Lehrerkürzel, welches für die Eingabe freigeschaltet ist. Das Klassenlehrerkürzel steht in $C$3 und der Klassenlehrer soll alle Felder in den Zeilen 4-40 bearbeiten dürfen.

Blatt 2 ("Login_Daten"): Eine Tabelle mit den Spalten Kürzel und Passwort, Klasse (diese entspricht dem Blattnamen) Hinweis: Aus Sicherheitsgründen sollten die Passwörter in der Datei idealerweise als Hash (z. B. bcrypt) vorliegen, nicht im Klartext.

Phase 2: Python Backend (FastAPI)
Python eignet sich hier perfekt, um die Brücke zwischen Web und Datei zu schlagen.

Bibliotheken wählen: fastapi (für die API), uvicorn (Server) und ezodf oder odfpy (für den LibreOffice-Zugriff).

API-Endpoints definieren:

POST /login: Gleicht Kürzel und Passwort mit Blatt 2 der .ods-Datei ab. Bei Erfolg wird ein temporäres Token (JWT) erstellt.

GET /students: Prüft das Token, liest z.B die Spalten A9:B24 und D9:D24 (die Grenzen sollten einstellbar sein. Eine Zeile (einstellbar) enthält alle Lehrerkürzel, so dass diese dann die Spalte ausfüllen dürfen) aus und schickt sie ans Frontend.

POST /submit-grades: Empfängt die eingegebenen Noten, schreibt sie in Spalte D9:D24 der Datei und speichert die Datei ab.

Protokollierung (Logging): Bei jedem erfolgreichen POST /submit-grades schreibt Python einen Eintrag in eine protokoll.txt (oder eine separate Tabelle in der .ods):

Zeitstempel | Kürzel | Schüler X | Note Y

Phase 3: React Frontend
Das Frontend dient als minimalistische, barrierefreie Oberfläche für die Kollegen.

Login-Maske: Einfaches Formular für Lehrerkürzel und Passwort.

Noten-Matrix: Eine übersichtliche Tabelle, die die Schülernamen (A9:B24) anzeigt. Daneben befinden sich Input-Felder für Spalte D.

Validierung: Das Frontend blockiert falsche Eingaben (z.B. Text statt Noten), bevor sie überhaupt abgeschickt werden.

Speicher-Button: Schickt die Daten gesammelt an das Backend.

Phase 4: Dockerisierung & Deployment
Damit die App überall läuft, verpacken wir sie in Docker.

Dockerfile für Backend: Installiert Python, die Abhängigkeiten und startet den FastAPI-Server.

Dockerfile für Frontend: Baut die React-App (z. B. via Vite) und liefert sie über einen schlanken Nginx-Webserver aus.

docker-compose.yml: Verbindet beide Container. Wichtig: Die .ods-Datei und das Protokoll werden über ein Docker Volume vom Host-System in den Backend-Container gemountet, damit die Daten beim Neustart des Containers nicht verloren gehen.

⚠️ Wichtige Praxis-Hinweise (Fallstricke vermeiden)
🛑 Gleichzeitige Zugriffe (Race Conditions): > Wenn Lehrer A und Lehrer B exakt gleichzeitig Noten abspeichern, könnte eine Eingabe die andere überschreiben.
Lösung: Implementiere im Python-Backend eine einfache Sperre (File-Locking oder eine globale Variable is_saving = True), sodass Anfragen nacheinander abgearbeitet werden.

🔒 Sicherheit im Docker-Container:
Da Lehrer von außen auf die App zugreifen, sollte der Docker-Container auf dem Server zwingend hinter einem Reverse-Proxy (wie Nginx Proxy Manager oder Traefik) mit HTTPS (SSL-Zertifikat) laufen. Passwörter dürfen niemals unverschlüsselt über HTTP übertragen werden.