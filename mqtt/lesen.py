#!/usr/bin/env python3
"""Zeigt MQTT-Nachrichten eines Roboters lesbar im Terminal an."""
import argparse
import importlib
import os

from common import env_value, load_config, robot_id

try:
    mqtt = importlib.import_module('paho.mqtt.client')
except ImportError as exc:
    raise SystemExit('paho-mqtt fehlt. Installation: python3 -m pip install --user paho-mqtt') from exc


def main():
    parser = argparse.ArgumentParser(description='SmartCity-MQTT-Nachrichten lesen')
    parser.add_argument('--config', default=os.path.join(os.path.dirname(__file__), 'config.yaml'))
    parser.add_argument('--robot', help='Roboter-ID; Standard aus Konfiguration/Umgebung')
    args = parser.parse_args()
    config = load_config(args.config)
    robot = args.robot or robot_id(config)
    broker = config.get('broker', {})
    client = mqtt.Client(client_id=f"smartcity-reader-{os.getpid()}")
    username = env_value(broker, 'username')
    if username:
        client.username_pw_set(username, env_value(broker, 'password'))
    if broker.get('tls'):
        client.tls_set()

    def on_connect(client, userdata, flags, rc):
        if rc:
            raise RuntimeError(f'Broker-Verbindung fehlgeschlagen (RC {rc})')
        topic = f"{config.get('base_topic', 'smartcity/robots').rstrip('/')}/{robot}/#"
        client.subscribe(topic, qos=1)
        print(f'Abonniert: {topic}')

    def on_message(client, userdata, message):
        print(f'[{message.topic}] {message.payload.decode("utf-8", errors="replace")}')

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(str(broker.get('host', '127.0.0.1')), int(broker.get('port', 1883)),
                   int(broker.get('keepalive', 30)))
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        client.disconnect()


if __name__ == '__main__':
    main()
