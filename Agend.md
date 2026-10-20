# Agenda SmartCity-Roboter

Stand: 20.10.2026

Diese Agenda sammelt die naechsten Arbeitsschritte fuer das gesamte Projekt. Neue Fahrfunktionen werden zuerst in der Simulation, danach im TEST-Modus und erst zuletzt auf dem echten Roboter geprueft.

## 1. Sicherheits- und Testgrundlage

- [ ] Sicherheitsablauf vor jeder Fahrt pruefen: STOPP-Knopf, `scripts/stopp.sh`, Watchdog und TEST-Modus.
- [ ] Einen festen Abnahmelauf fuer die Simulation dokumentieren und regelmaessig mit `scripts/simulation.sh pruefen` ausfuehren.
- [ ] Testprotokoll fuer RM02 fuehren: Datum, Softwarestand, Konfiguration, Ergebnis und offene Probleme.
- [ ] Alle neuen Einstellungen in `config/lokal/` halten und nicht in die Standardkonfiguration einchecken.

## 2. Naechster Entwicklungsblock: Navigation

### Kreuzungen und Abbiegen

- [ ] Kreuzungen K1-K8 im Stadtplan modellieren.
- [ ] T-Einmuendungen und Kreuzungen unterscheiden.
- [ ] Einbahnrichtungen auswerten und unzulaessige Fahrwege verhindern.
- [ ] Abbiegeentscheidung aus Ziel, Stadtplan und aktueller Position ableiten.
- [ ] Abbiegen in der Simulation testen: links, rechts, geradeaus und Wenden.
- [ ] Linienfolger und KI-Zentrale so verbinden, dass die geplante Richtung eindeutig ist.

### Wegwahl und Ziele

- [ ] Zufaellige, aber abwechslungsreiche Wegwahl implementieren.
- [ ] Erreichte Knoten und bereits gefahrene Strecken beruecksichtigen.
- [ ] Spaeter ein Zielsystem fuer `fahr zu X` ergaenzen.
- [ ] Verhalten bei ungueltigem, unbekanntem oder blockiertem Ziel festlegen.

## 3. Verkehr und Roboterausstattung

- [ ] Abblendlicht ueber die vordere LED-Leiste steuern.
- [ ] Blinker passend zu Abbiegeentscheidung und Abbiegevorgang ansteuern.
- [ ] LED- und Blinkerzustand im Panel anzeigen.
- [x] Erste MQTT-Bridge mit konfigurierten ROS2-Topics, JSON-Huelle und MQTT-Leser implementieren.
- [ ] MQTT-Schnittstelle fuer die Leitzentrale mit Broker-/Dashboardteam final abstimmen.
- [ ] MQTT-Nachrichten fuer vollstaendigen Status, Position, Entscheidung, Fehler und STOPP festlegen.
- [ ] MQTT in der Simulation mit einem einfachen Gegenpart testen.
- [ ] VLAN-Konfiguration auf allen Robotern pruefen und dokumentieren.

## 4. Greifarm und Hindernisse

- [ ] Armbewegungen auf dem echten RM02 testen.
- [ ] Greiferstellung offen/geschlossen und Fahrstellung im Panel pruefen.
- [ ] Kameraposition und Armmasse am echten Roboter nachmessen.
- [ ] Hindernis aufnehmen, ablegen und anschliessend den Weg erneut pruefen.
- [ ] Fehlversuche, Abbruch nach vier Versuchen und Verhalten bei Personen/Tieren/Fahrzeugen testen.
- [ ] Ergebnisse der Armtests in `docs/greifarm.md` dokumentieren.

## 5. Sensorik und Karte am echten Roboter

- [ ] Kamerahoehe und Kameraeinstellung messen und in `config/lokal/roboter.yaml` korrigieren.
- [ ] LiDAR-Richtung und Position ueber eine Messfahrt verifizieren.
- [ ] IMU-Richtung und Odometrie mit realen Messwerten pruefen.
- [ ] Zweiten LiDAR auf dem echten Roboter kalibrieren.
- [ ] 2D- und 3D-Karte ueber mehrere Runden vergleichen.
- [ ] Abweichungen und Messfahrt-Dateien in `docs/karte.md` festhalten.

## 6. KI und Linienfolger

- [ ] Ampelerkennung mit den verwendeten Modellampeln verbessern und auf RM02 testen.
- [ ] YOLO-Erkennungen mit eigenen SmartCity-Motiven bewerten.
- [ ] Auslastung und Bildrate der KI auf dem Jetson messen.
- [ ] Verhalten bei alten oder fehlenden Kamerabildern pruefen: langsamer werden, dann STOPP.
- [ ] Linienfolger bei verschiedenen Geschwindigkeiten, Kurven und Kreuzungen testen.
- [ ] Hindernis-, Zebrastreifen-, Stoppschild- und Einbahnstrassenregeln als Simulationstest absichern.

## 7. Panel und Betrieb

- [ ] Dashboard um Navigationsziel, Abbiegerichtung, Licht und MQTT-Status erweitern.
- [ ] Fehlermeldungen und letzte Entscheidungen nachvollziehbar anzeigen.
- [ ] STOPP auf jeder Panel-Seite erreichbar halten.
- [ ] Bedienung auf 1024x600, Handy und Laptop pruefen.
- [ ] Zugriff aus dem Netzwerk bewusst aktivieren/deaktivieren und im Systemcheck anzeigen.
- [ ] Update, Installation und Not-Aus auf einem frisch eingerichteten System testen.

## 8. Vier-Roboter-Betrieb

- [ ] Fuer RM01, RM02, RM03 und RM04 eindeutige ROS-Domain-IDs vergeben.
- [ ] Robotername, IP-Adresse und VLAN je Roboter dokumentieren.
- [ ] Gleichzeitige Kommunikation ohne Topic-Konflikte testen.
- [ ] Leitzentrale und MQTT mit vier Robotern testen.
- [ ] Verhalten bei Netzwerkausfall, Roboter-STOPP und Wiederanlauf festlegen.

## 9. Qualitaet und Dokumentation

- [ ] Automatische Tests nach jeder relevanten Aenderung ausfuehren.
- [ ] Neue Funktionen mit mindestens einem Simulations- oder Unit-Test absichern.
- [ ] Dokumentation aktualisieren, sobald Bedienung, Konfiguration oder Verhalten geaendert wird.
- [ ] Bekannte Fehler in `README.md` und den passenden Dateien aktuell halten.
- [ ] Vor einer Vorfuehrung einen kompletten Durchlauf mit TEST, START und STOPP dokumentieren.

## Prioritaeten

1. Sicherheitsablauf und reale Sensorik auf RM02 verifizieren.
2. Kreuzungen, Abbiegen und Wegwahl in der Simulation fertigstellen.
3. Greifarm und Hindernisraeumung am echten Roboter testen.
4. Licht, MQTT und VLAN fuer den Betrieb vorbereiten.
5. Vier-Roboter-Betrieb und Vorfuehrungsabnahme durchfuehren.

## Definition of Done

Eine Aufgabe gilt als erledigt, wenn:

- die Funktion implementiert und dokumentiert ist,
- ein passender automatischer Test oder Simulationslauf erfolgreich ist,
- der TEST-Modus das Verhalten sichtbar bestaetigt,
- reale Hardwaretests bei sensor- oder fahrrelevanten Aenderungen erfolgreich sind,
- und offene Risiken im Testprotokoll festgehalten wurden.
