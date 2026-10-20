#!/usr/bin/env python3
"""Laedt gespeicherte Karten aus MQTT-Chunks und setzt die Dateien zusammen."""
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path

from common import env_value, load_config, robot_id

try:
    mqtt = importlib.import_module('paho.mqtt.client')
except ImportError as exc:
    raise SystemExit('paho-mqtt fehlt. Installation: python3 -m pip install --user paho-mqtt') from exc


def sicherer_name(value):
    return value and value not in ('.', '..') and '/' not in value and '\\' not in value


def main():
    parser = argparse.ArgumentParser(description='Gespeicherte Karten aus MQTT herunterladen')
    parser.add_argument('--config', default=os.path.join(os.path.dirname(__file__), 'config.yaml'))
    parser.add_argument('--robot', help='Roboter-ID; Standard aus Konfiguration/Umgebung')
    parser.add_argument('--output', default='mqtt_karten', help='Ausgabeordner')
    args = parser.parse_args()
    config = load_config(args.config)
    robot = args.robot or robot_id(config)
    base = config.get('base_topic', 'smartcity/robots').rstrip('/')
    prefix = f'{base}/{robot}/maps/'
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    index = {}
    chunk_root = output / '.chunks'
    broker = config.get('broker', {})
    client = mqtt.Client(client_id=f'smartcity-map-reader-{os.getpid()}')
    username = env_value(broker, 'username')
    if username:
        client.username_pw_set(username, env_value(broker, 'password'))
    if broker.get('tls'):
        client.tls_set()

    def assemble(map_name, file_name):
        meta = index.get(map_name, {}).get('files', {}).get(file_name)
        if not meta or not sicherer_name(map_name) or not sicherer_name(file_name):
            return
        expected = int(meta.get('chunks', 0))
        parts = [chunk_root / map_name / file_name / f'{number:06d}' for number in range(expected)]
        if not all(part.is_file() for part in parts):
            return
        target = output / map_name / file_name
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + '.neu')
        with temporary.open('wb') as stream:
            for part in parts:
                with part.open('rb') as source:
                    stream.write(source.read())
        expected_hash = meta.get('sha256')
        if expected_hash:
            digest = hashlib.sha256()
            with temporary.open('rb') as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(block)
            if digest.hexdigest() != expected_hash:
                temporary.unlink()
                print(f'FEHLER: Hash stimmt nicht: {map_name}/{file_name}')
                return
        temporary.replace(target)
        print(f'Karte gespeichert: {target} ({target.stat().st_size} Bytes)')

    def on_connect(client, userdata, flags, rc):
        if rc:
            raise RuntimeError(f'Broker-Verbindung fehlgeschlagen (RC {rc})')
        client.subscribe(prefix + '#', qos=1)
        print(f'Abonniert: {prefix}#')

    def on_message(client, userdata, message):
        if not message.topic.startswith(prefix):
            return
        suffix = message.topic[len(prefix):]
        if suffix == 'index':
            try:
                daten = json.loads(message.payload.decode('utf-8'))
                index.clear()
                index.update({item['name']: item for item in daten.get('maps', [])
                              if sicherer_name(item.get('name', ''))})
                (output / 'index.json').write_text(json.dumps(daten, indent=2), encoding='utf-8')
                print(f"Kartenindex empfangen: {', '.join(sorted(index)) or 'keine Karten'}")
                for map_name, item in index.items():
                    for file_name in item.get('files', {}):
                        assemble(map_name, file_name)
            except (UnicodeDecodeError, ValueError, KeyError) as exc:
                print(f'Fehler im Kartenindex: {exc}')
            return
        teile = suffix.split('/')
        if len(teile) != 4 or teile[1] != 'files' or not sicherer_name(teile[0]) or not sicherer_name(teile[2]):
            return
        try:
            nummer = int(teile[3])
        except ValueError:
            return
        ziel = chunk_root / teile[0] / teile[2] / f'{nummer:06d}'
        ziel.parent.mkdir(parents=True, exist_ok=True)
        ziel.write_bytes(message.payload)
        assemble(teile[0], teile[2])

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
