#!/bin/bash
# Startet die ROS2 -> MQTT-Bridge.
source "$(dirname "$0")/env.sh"

if ! python3 -c 'import paho.mqtt.client' 2>/dev/null; then
    echo 'paho-mqtt fehlt. Installation: python3 -m pip install --user paho-mqtt' >&2
    exit 1
fi

exec python3 "$REPO_DIR/mqtt/bridge.py" --config "$REPO_DIR/mqtt/config.yaml"
