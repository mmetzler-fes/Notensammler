### Container-Spezifikationen
1. **Frontend Container:** React (Vite), SPA ausgeliefert über Nginx, Single Sign-On (SSO) Integration.
2. **Backend Container:** Python FastAPI, Uvicorn, integrierte ODS-Verarbeitung, Anbindung an Authentifizierungsschnittstelle.
3. **Datenbank (optionaler Container):** PostgreSQL für Produktionsumgebungen (SQLite für lokale Tests).

---

## 🗄️ 2. Datenbankdesign

Das relationale Datenbankschema wird über SQLAlchemy-Modelle im Backend definiert.

### Tabelle: `Klassen`
* `Klasse` (VARCHAR, Primary Key)
* `Klassenlehrer` (VARCHAR)

### Tabelle: `Deputat`
* `eintrag` (INTEGER, Primary Key, Autoincrement)
* `Lehrerkuerzel` (VARCHAR)
* `Klasse` (VARCHAR, Foreign Key -> Klassen.Klasse)
* `Gruppe` (VARCHAR, Nullable)
* `Deputat` (VARCHAR)

### Tabelle: `Notenblatt`
* `eintrag` (INTEGER, Primary Key, Autoincrement)
* `Kategorie` (VARCHAR) – *z.B. BFK, PK, Verhalten, Mitarbeit*
* `Klasse` (VARCHAR, Foreign Key)
* `Gruppe` (VARCHAR, Nullable)
* `halbjahr` (INTEGER) – *Wert: 1 oder 2*
* `Lehrerkuerzel` (VARCHAR)
* `Fach` (VARCHAR) – *Fokus auf BT, BT-L, BT-W*
* `Gewichtung` (FLOAT)

### Tabelle: `Schueler`
* `schuelerid` (VARCHAR/INTEGER, Primary Key)
* `Name` (VARCHAR)
* `Vorname` (VARCHAR)
* `Klasse` (VARCHAR, Foreign Key)

### Tabelle: `Noteneintrag`
* `eintrag_id` (INTEGER, Primary Key, Autoincrement)
* `schuelerid` (VARCHAR/INTEGER, Foreign Key)
* `lehrer` (VARCHAR)
* `fach` (VARCHAR)
* `halbjahr` (INTEGER) – *1 oder 2 (Jahr)*
* `note` (NUMERIC) – *Ergänzt für die tatsächliche Notenspeicherung*

---

## ⚙️ 3. ETL-Prozess & Gewichtungs-Engine (Core-Logik)

Die Kernkomponente ist ein Python-Parser (unter Verwendung von `pandas` und `odfpy`), der die Quelldateien einliest, validiert und transformiert.

### Ablaufschritte (Pipeline)
1. **Klassen-Import:** `Vorlage_Klassen.ods` einlesen und die Tabelle `Klassen` befüllen.
2. **Deputat-Import & Filterung:** `Deputat.ods` (oder `.xlsx`) einlesen. Alle Datensätze verwerfen, deren Spalte `Klasse` nicht in der Tabelle `Klassen` existiert.
3. **Gewichtungsberechnung:** Jede gültige Zeile durchläuft die `calculate_weight()`-Engine basierend auf dem Feld `Deputat`.

### 📊 Parsing-Regeln für die Gewichtung
Die Berechnung ermittelt für jeden Deputatseintrag die Gewichtung pro Halbjahr (HJ1 und HJ2):

| Deputat-Muster | Beispiel | Logik Halbjahr 1 (HJ1) | Logik Halbjahr 2 (HJ2) |
| :--- | :--- | :--- | :--- |
| **1 Ziffer** | `1` | `1.0` | `1.0` |
| **2 Ziffern** | `12` | `0.5` | `0.5` |
| **Präfix A** | `A14` | Wert der Folgeziffern (z.B. `14` -> 0.25) | `0.0` |
| **Präfix B** | `B12` | `0.0` | Wert der Folgeziffern (z.B. `12` -> 0.5) |
| **Präfix C, D** | `C12` | Halbe Anrechnung der Folgeziffern (z.B. `12` -> 0.5 * 0.5 = `0.25`) | `0.0` |
| **Präfix E, F** | `E1` | `0.0` | Halbe Anrechnung der Folgeziffern (z.B. `1` -> 1.0 * 0.5 = `0.5`) |
| **Blockunterricht** | `BLO1` | Basierend auf Spalte M (Blockeinträge) und Spalte B (Schulwochen im HJ1): `Einträge / Schulwochen` | Basierend auf Spalte M und Spalte B für das 2. Halbjahr |

### ➕ Generierung von Sonderzeilen (Automatische Notenblatt-Einträge)
Nach der Verarbeitung des regulären Unterrichts (BT, BT-L, BT-W) werden für jede Klasse automatisch folgende System-Einträge in `Notenblatt` erzeugt:
* **PK Note:** Ein Eintrag für jeden in der Klasse unterrichtenden Lehrer mit der Gewichtung `1.0`.
* **Verhalten & Mitarbeit:** Ein Eintrag für jeden Lehrer, der im jeweiligen Halbjahr aktiv in der Klasse unterrichtet hat, mit der Gewichtung `1.0`.

---

## 📄 4. ODS-Template-Export-Engine

Die Transformation der Datenbankeinträge zurück in klassenspezifische ODS-Dateien erfolgt spaltenweise ab **Spalte E**.

### Generierungs-Logik

#### Variante A: Halbjahr 1 (`klasse_1HJ.ods`)
* Berücksichtigt ausschließlich Einträge aus `Notenblatt` mit `halbjahr == 1`.
* Befüllung des Templates:
  * **Zeile 4:** Fach
  * **Zeile 5:** Lehrerkürzel
  * **Zeile 6:** Gewichtung
  * **Zusatz:** Falls Unterricht nur in Gruppe (z.B. "Gr.A"), Eintrag des Gruppensuffixes.
* Der Spaltenzeiger inkrementiert nach jedem Eintrag von links nach rechts (Spalte E -> F -> G...).

#### Variante B: Ganzjahr (`klasse_Jahr.ods`)
* Führt die Daten aus HJ1 und HJ2 zusammen.
* **Fall 1 (Kontinuität):** Unterrichtet derselbe Lehrer dasselbe Fach in beiden Halbjahren, werden die Gewichte addiert (`Gewichtung_Gesamt = HJ1 + HJ2`) und in einer gemeinsamen Spalte ausgegeben.
* **Fall 2 (Wechsel):** Unterrichtet ein Lehrer *nur* im 2. Halbjahr, erhält er eine eigene, separate Spalte mit seiner spezifischen Gewichtung.

---

## 💻 5. Web-Applikation & Berechtigungskonzept

Nach Abschluss der Testphase (reiner Datei-Import/Export) wird die interaktive Benutzeroberfläche implementiert.

### Authentifizierung & Autorisierung
* **SSO-Anbindung:** Identitätsprüfung erfolgt über das zentrale Schul-SSO. Das Backend validiert das JWT (JSON Web Token).
* **Rollen & Rechte:**
  * **Fachlehrer:** Kann via GUI eine Klasse auswählen, sieht die Schülerliste und kann ausschließlich Noten für seine eigenen Fächer editieren (`Noteneintrag`).
  * **Klassenlehrer:** Besitzt administrative Rechte für seine zugeordnete Klasse. Kann Noten aller Fachlehrer einsehen und bei Bedarf korrigieren. Verfügt über den **"Button Export"**, welcher die Generierung und den Download der aktuellen `.ods`-Dateien triggert.

### Protokollierung
Jede sensitive Aktion (Notenänderung, Datei-Export, unberechtigter Zugriff) schreibt unverzüglich einen asynchronen Log-Eintrag in das Filesystem des Backends:
* Format: `[ZEITSTEMPEL] [USER_ID] [AKTION] [DETAILS] -> log_protokoll.txt`

---

## 🎯 6. Meilensteine & Test-Szenario für Phase 1

Um die korrekte Funktion der Gewichtungs-Engine isoliert zu prüfen, wird ein CLI-Testlauf aufgesetzt.

* [ ] **Meilenstein 1:** Erstellung des Python-Skripts zur fehlerfreien Berechnung aller Gewichtungen (inkl. `BLO`-Sonderlogik) anhand der Testdaten (`Deputat.ods` & `Vorlage_Klassen.ods`).
* [ ] **Meilenstein 2:** Erfolgreiches automatisiertes Ausfüllen und Abspeichern der ODS-Dateien auf Basis des `Vorlage.ods`-Templates. Die Schülerdaten bleiben in diesem Schritt definitionsgemäß leer.
* [ ] **Meilenstein 3:** Docker-Containerisierung von FastAPI und React sowie Implementierung der GUI für die Noteneingabe.
"""
