# MQTT-Bridge

Die Bridge liest konfigurierte ROS2-Topics und veroeffentlicht sie als versionierte JSON-Nachrichten am MQTT-Broker. Sie beeinflusst weder Motorbefehle noch lokale Fahrentscheidungen. ROS2 bleibt auch bei einem nicht erreichbaren Broker lauffaehig.

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
