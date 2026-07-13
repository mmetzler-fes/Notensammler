Single Sign On (SSO)
Vorlagen Schule:
- Deputat.ods (Deputatsplan Lehrer)
- Vorlage.ods (Ausgabe Template für Klassenlehrer) 
- Vorlage_Klassen (Relevante Klassen mit Klassenlehrer Kürzel)
- Ausbaustufe: Vorlage Schülerdaten (erfolgt später)
- Es soll eine Datenbank generiert werden, welche für alle Lehrer und Klassen, die in der Vorlage Klassen vorhanden sind
aus den Deputatsstunden eine Gewichtung für die BFK Note bilden. Die Note umfasst BT, BT-L und BT-W Unterricht

Mögliches Datenbankdesign
Tabelle Klassen:
- Klasse (PK)
- Klassenlehrer
Tabelle Deputat:
- eintrag (PK)
- Lehrerkuerzel 
- Klasse
- Gruppe
- Deputat
Tabelle Notenblatt
- eintrag (PK)
- Kategorie
- Klasse
- Gruppe
- HJ #1 oder 2
- Lehrerkuerzel
- Fach
- Gewichtung
Tabelle Schueler
- schuelerid (PK)
- Name
- Vorname
- Klasse
Tabelle Noteneintrag
- schuelerid (PK)
- lehrer
- fach
- halbjahr #(1 oder Jahr)

Beschreibung:
- Zunächst sollen für alle Klassen, die in Vorlage_Klassen.ods vorhanden sind die DB Tabelle Klassen ausgefüllt werden
- Für alle Deputatseinträge in Deputat.xlsx, welche auch in der DB Klassen Tabelle vorhanden sind, sollen diese Einträge in die DB Tabelle Deputat eingetragen werden. 
- Aus dem Deputat (Kürzel) soll die Gewichtung berechnet werden.
Regeln:
Deputat mit einer Ziffer 1:
- Gewichtung 1 je HJ
Deputat mit zwei Ziffern:
z.B. 12: Gewichtung 0,5 je HJ
14: Gewichtung 0,25 je HJ
Deputat mit Buchstaben voran:
A: im ersten Halbjahr Anrechnung der Ziffern im Anschluss. 
C,D: im ersten Halbjahr halbe Anrechnung der Ziffern im Anschluss. 
B: im zweiten Halbjahr Anrechnung der Ziffern im Anschluss. 
E,F: im zweiten Halbjahr halbe Anrechnung der Ziffern im Anschluss. 
BLO1, BLO2, BLO3, BLO4: die Anrechnung ergibt sich anhander der Blöcke je HJ (siehe Spalte M Blockunterricht und Spalte B Schulwoche) z.B. wenn im 1. Halbjahr (Spalte O) 5x Einträge bei
(Spalte B) 19 Schulwochen waren, dann ist die Gewichtung 5/19 im ersten HJ

- Alle Deputatseinträge werden in ein Notenblatt-Eintrag in der DB Tabelle Notenblatt umgeformt.

Aus allen Notenblatt Einträgen wird für jede Klasse aus der Tabelle Klassen ein Template ausgefüllt:
Für jede Klasse mit Einträgen in der Tabelle Deputat mit den Fächern zu BT, BT-L und BT-W wird für jeweils das 1.HJ, 2.HJ das Fach (Zeile 4 Spalte E-R), das Lehrerkürzel (Zeile 5), die Gewichtung (Zeile 6) und bei Unterricht nur in einer Gruppe Gr.A oder Gr.B eingetragen.
Die Spalten werden nach dem Eintrag hochgezählt.
Bei der PK Note wird für alle Lehrer genau ein Eintrag mit dem Lehrerkürzel und dem Gewicht 1 erzeugt.
Beim Verhalten und Mitarbeit wird für alle Lehrer der Klasse (die im entsprechenden HJ unterrichtet haben) genau ein Eintrag mit dem Lehrerkürzel und der Gewichtung 1 erzeugt.

Die Schülerdaten werden separat in die Tabelle Schülerdaten eingepflegt. 
Die Notendaten sollen im Anschluss über eine Web-App von den Lehrern selbstständig eingegeben werden können -> DB Tabelle Noteneintrag

Konvertierung in ODS-Tabellen
Für jede Klasse soll anhand der Vorlage eine .ods Datei mit dem Namen klasse_1HJ.ods oder klasse_Jahr.ods erzeugt werden.
Für die Tabellenblatt 1HJ werden nur Deputate des 1HJ berücksichtigt. Für das Jahr werden Werte mit dem ersten HJ verrechnet (Gewichtung wird addiert) und wenn Lehrer nur im 2.HJ unterrichten als wird ein Eintrag als separate Spalte mit der entsprechenden Gewichtung angezeigt.

Test: Anhand der Beispieltabelle (Deputat.ods, Vorlage_Klassen.ods, Vorlage.ods) soll für jede Klasse eine Tabelle mit den korrekten Gewichtungen generiert werden.
Die Schülerdaten bleiben im ersten Test noch leer.

Webapp (folgt später)
Später soll es über eine Webapp möglich sein, dass jeder Lehrer separat die Note eingibt -> Eintrag in die DB
Der Klassenlehrer soll die ods-Datei bei Bedarf generieren können anhand der vorhandenen Einträge (Datenbank Einträge)

[ Webbrowser (Lehrer) SSO ] 
       │ (HTTPS / REST)
       ▼
[ React Frontend (Docker Container 1) ]
       │
       ▼
[ Python FastAPI Backend (Docker Container 2) ]
       │
       ├──► Liest/Schreibt: Datenbank
       -> Auswahl Klasse
       -> Noteneingabe für Lehrer, die in der Klasse unterrichten
       -> Klassenlehrer kann alle Noten eingeben/ändern (auch von anderen Fachlehrern)
       -> Zeigt eigene Notendaten an (bzw. alle für Klassenlehrer)
       -> Exportiert Notendaten (Button Export) für den Klassenlehrer
       └──► Schreibt: log_protokoll.txt


