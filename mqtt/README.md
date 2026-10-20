# MQTT-Bridge

Die Bridge verbindet den Roboter in beide Richtungen mit dem MQTT-Broker:

- **Roboter -> Broker:** konfigurierte ROS2-Topics als versionierte JSON-Nachrichten (Status, Position, Ereignisse, Karten).
- **Broker -> Roboter:** nur freigegebene Befehle (STOPP, TEST, Tempo; START nur nach Freigabe). Sie laufen ueber die lokale Panel-API, also mit denselben Pruefungen wie die Panel-Knoepfe.

ROS2 und die lokale Fahrt bleiben auch bei einem nicht erreichbaren Broker lauffaehig. Ist der Broker beim Start noch nicht erreichbar, verbindet sich die Bridge automatisch, sobald er da ist.

## Einrichtung

1. In `config.yaml` die Broker-Adresse, den Port und die Topic-Auswahl eintragen.
2. Zugangsdaten als Umgebungsvariablen setzen, zum Beispiel:

```bash
export MQTT_USERNAME='roboter-rm02'
export MQTT_PASSWORD='passwort-nicht-ins-repository'
export SMARTCITY_ROBOT_ID='RM02'
```

3. Paho MQTT installieren:

```bash
python3 -m pip install --user paho-mqtt
```

Funktioniert mit paho-mqtt 1.x und 2.x.

## Starten

Auf dem Roboter, nachdem ROS2 und die Sensoren laufen:

```bash
scripts/mqtt_bridge.sh
```

Die Bridge wird beim Start des Panels automatisch mitgestartet. Der Broker darf trotzdem nicht erreichbar sein; die lokale Fahrt bleibt davon unabhaengig.

## Nachrichten lesen

```bash
python3 mqtt/lesen.py --robot RM02
```

Topics folgen diesem Muster:

```text
smartcity/robots/RM02/state/ki_befehl
smartcity/robots/RM02/state/line_follower
smartcity/robots/RM02/events
smartcity/robots/RM02/availability
smartcity/robots/RM02/info
smartcity/robots/RM02/state/bridge
smartcity/robots/RM02/cmd          (Befehle an den Roboter)
smartcity/robots/RM02/cmd/result   (Antworten des Roboters)
smartcity/robots/all/cmd           (Befehle an alle Roboter)
smartcity/robots/RM02/maps/index
smartcity/robots/RM02/maps/smartcity/files/karte.png/000000
```

Jede Nachricht enthaelt unter anderem `schema_version`, `robot_id`, `boot_id`, `seq`, `generated_at`, `ros_topic`, `ros_type` und `payload`. Die Status-Topics werden retained mit QoS 1 gesendet; Ereignisse und Scans nicht retained.

## Position und Karten

Die laufende Position kommt aus `/karte/pose` und wird unter `state/karte` als JSON veroeffentlicht. Der Kartenindex liegt unter `maps/index` und listet alle Ordner unter `karten/` mit Dateigroesse, Aenderungszeit und Chunk-Anzahl.

Die Dateien einer Karte werden als retained Binaer-Nachrichten veroeffentlicht:

```text
smartcity/robots/RM02/maps/<kartenname>/files/karte.json/000000
smartcity/robots/RM02/maps/<kartenname>/files/karte.png/000000
smartcity/robots/RM02/maps/<kartenname>/files/karte.ply/000000
smartcity/robots/RM02/maps/<kartenname>/files/karte.npz/000000
smartcity/robots/RM02/maps/<kartenname>/files/wolke.bin/000000
```

Bei grossen Dateien folgen weitere sechsstellige Chunk-Nummern. Der Index muss zuerst gelesen werden; daraus ergeben sich die vorhandenen Karten und die benoetigte Chunk-Anzahl.

Zum Herunterladen und Zusammensetzen der Karten auf dem Laptop oder Server:

```bash
python3 mqtt/karten_holen.py --robot RM02 --output mqtt_karten
```

Der Prozess bleibt aktiv und uebernimmt auch spaeter aktualisierte Karten. Mit `Strg+C` beenden.

## Befehle an den Roboter

Das Dashboard bzw. die Leitzentrale schickt Befehle nicht retained mit QoS 1 an `smartcity/robots/<ID>/cmd` (oder `smartcity/robots/all/cmd` fuer alle):

```json
{"id": "8f3c...", "befehl": "stopp", "von": "Leitzentrale", "gesendet": 1792500000.5}
{"id": "8f3d...", "befehl": "tempo", "wert": 0.2, "gesendet": 1792500001.0}
```

| Feld | Bedeutung |
|---|---|
| `befehl` | `stopp`, `test`, `start` oder `tempo` (ein einfacher Text wie `stopp` geht auch) |
| `id` | frei waehlbar; kommt in der Antwort zurueck, doppelte IDs werden nur einmal ausgefuehrt |
| `wert` | nur bei `tempo`: Geschwindigkeit in m/s (das Panel begrenzt auf 0,05 bis 0,4) |
| `gesendet` | Unix-Zeit in Sekunden; aeltere Befehle als `commands.max_age_seconds` werden verworfen (ausser STOPP) |
| `von` | Absender, erscheint als Ereignis im Panel |

Die Antwort kommt unter `smartcity/robots/<ID>/cmd/result`:

```json
{"id": "8f3c...", "befehl": "stopp", "ok": true, "antwort": "Gestoppt", "robot_id": "RM02", "generated_at": "..."}
```

Regeln:

- **STOPP** ist immer erlaubt. Die Bridge sendet sofort Stillstand an `/cmd_vel` und beendet dann ueber das Panel den Linienfolger. Laeuft das Panel nicht, wird trotzdem Stillstand gesendet.
- **START** ist standardmaessig gesperrt, weil jeder mit den Broker-Zugangsdaten den Roboter sonst losfahren lassen koennte. Freigabe in `config.yaml` unter `commands.allowed`.
- **Retained-Befehle werden nie ausgefuehrt**, sonst wuerde ein alter Befehl nach jedem Neuverbinden erneut ausgeloest.
- `info` listet unter `befehle`, was dieser Roboter annimmt.

Testen ohne Roboter (startet einen lokalen Test-Broker):

```bash
python3 -m pip install --user paho-mqtt amqtt
python3 tests/test_mqtt.py
```
