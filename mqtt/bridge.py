#!/usr/bin/env python3
"""Nicht blockierende ROS2 <-> MQTT-Bridge fuer die SmartCity-Roboter.

Richtung Broker: konfigurierte ROS2-Topics als JSON. Richtung Roboter: nur freigegebene Befehle
(STOPP, TEST, START, Tempo) ueber <base>/<roboter>/cmd und <base>/all/cmd. Diese gehen an die lokale
Panel-API, damit dieselben Sicherheitspruefungen gelten wie beim Knopf im Panel.
"""
import argparse
import hashlib
import json
import os
import queue
import signal
import threading
import time
import urllib.request
import uuid
from pathlib import Path

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rosidl_runtime_py.convert import message_to_ordereddict
from rosidl_runtime_py.utilities import get_message
from std_msgs.msg import String

try:
    import paho.mqtt.client as mqtt
except ImportError:
    mqtt = None

from common import befehl_pruefen, dumps, load_config, mqtt_client, robot_id, utc_now

REPO = Path(__file__).resolve().parent.parent


class MqttBridge(Node):
    def __init__(self, config):
        super().__init__('smartcity_mqtt_bridge')
        self.config = config
        self.robot = robot_id(config)
        self.boot_id = str(uuid.uuid4())
        self.seq = 0
        self.queue = queue.Queue(maxsize=int(config.get('queue_size', 100)))
        self.max_payload = int(config.get('max_payload_bytes', 262144))
        self.ros_abos = {}
        self.mqtt_client = None
        self.mqtt_connected = False
        self.publish_errors = 0
        self.running = True
        self.map_signatures = {}
        self.map_hashes = {}
        befehle = config.get('commands', {})
        self.befehle_aktiv = bool(befehle.get('enabled', True))
        self.befehle_erlaubt = set(befehle.get('allowed', ['stopp']))
        self.befehl_max_alter = float(befehle.get('max_age_seconds', 10))
        self.panel_url = str(befehle.get('panel_url', 'http://127.0.0.1:8080')).rstrip('/')
        self.letzte_befehl_ids = []
        self.befehle_angenommen = 0
        self.befehle_abgelehnt = 0
        self.worker = threading.Thread(target=self._publish_loop, daemon=True)
        self.worker.start()
        self.status_pub = self.create_publisher(String, '/mqtt/status', 10)
        self.cmd_pub = self.create_publisher(Twist, '/cmd_vel', 10)
        self.ereignis_pub = self.create_publisher(String, '/ki/ereignis', 10)
        self._connect_mqtt()
        self._load_subscriptions()
        self.create_timer(2.0, self._status)
        self.create_timer(float(config.get('maps', {}).get('interval_seconds', 10)), self._publish_maps)
        self.get_logger().info(f'MQTT-Bridge fuer {self.robot} gestartet (Boot-ID {self.boot_id})')

    def _topic(self, suffix):
        return f"{self.config.get('base_topic', 'smartcity/robots').rstrip('/')}/{self.robot}/{suffix.lstrip('/')}"

    def _connect_mqtt(self):
        if mqtt is None:
            self.get_logger().error('paho-mqtt fehlt. Installation: python3 -m pip install --user paho-mqtt')
            return
        broker = self.config.get('broker', {})
        client_id = f"{broker.get('client_id_prefix', 'smartcity-bridge')}-{self.robot}-{os.getpid()}"
        self.mqtt_client = mqtt_client(mqtt, client_id, broker)
        availability = self._topic('availability')
        self.mqtt_client.will_set(availability, 'offline', qos=1, retain=True)
        self.mqtt_client.on_connect = self._on_connect
        self.mqtt_client.on_disconnect = self._on_disconnect
        self.mqtt_client.on_message = self._on_befehl
        try:
            # async: Ist der Broker beim Start nicht erreichbar, versucht paho es im Hintergrund weiter
            self.mqtt_client.reconnect_delay_set(1, 30)
            self.mqtt_client.connect_async(str(broker.get('host', '127.0.0.1')), int(broker.get('port', 1883)),
                                           int(broker.get('keepalive', 30)))
            self.mqtt_client.loop_start()
        except Exception as exc:
            self.get_logger().error(f'MQTT-Verbindung fehlgeschlagen: {exc}')

    def _on_connect(self, client, userdata, flags, rc):
        self.mqtt_connected = rc == 0
        if self.mqtt_connected:
            self._enqueue(self._topic('availability'), 'online', 1, True)
            info = {'schema_version': '1.0', 'robot_id': self.robot, 'boot_id': self.boot_id,
                    'software': 'smartcity-roboter', 'capabilities': ['ros2-telemetry'],
                    'befehle': sorted(self.befehle_erlaubt | {'stopp'}) if self.befehle_aktiv else []}
            if self.befehle_aktiv:
                info['capabilities'].append('commands')
                base = self.config.get('base_topic', 'smartcity/robots').rstrip('/')
                client.subscribe([(self._topic('cmd'), 1), (f'{base}/all/cmd', 1)])
            self._enqueue(self._topic('info'), dumps(info), 1, True)
            self.get_logger().info('MQTT-Broker verbunden')
        else:
            self.get_logger().error(f'MQTT-Verbindung abgelehnt (RC {rc})')

    def _on_disconnect(self, client, userdata, rc):
        self.mqtt_connected = False
        if self.running:
            self.get_logger().warn(f'MQTT-Broker getrennt (RC {rc})')

    def _on_befehl(self, client, userdata, message):
        """Befehl vom Broker (laeuft im paho-Thread, darf nicht blockieren)."""
        befehl, fehler = befehl_pruefen(message.payload, message.retain, self.befehle_erlaubt,
                                        self.befehl_max_alter)
        if befehl is not None and befehl.get('id') is not None:
            if befehl['id'] in self.letzte_befehl_ids:
                return                          # QoS 1 kann doppelt zustellen
            self.letzte_befehl_ids = (self.letzte_befehl_ids + [befehl['id']])[-50:]
        if fehler:
            self.befehle_abgelehnt += 1
            self.get_logger().warn(f'MQTT-Befehl abgelehnt: {fehler}', throttle_duration_sec=5)
            antwort = {'befehl': None, 'ok': False, 'antwort': fehler}
            try:
                antwort.update(id=json.loads(message.payload).get('id'))
            except (ValueError, AttributeError, TypeError):
                pass
            return self._befehl_antwort(antwort)
        self.befehle_angenommen += 1
        if befehl['befehl'] == 'stopp':
            self.cmd_pub.publish(Twist())       # sofort, auch wenn das Panel nicht laeuft
        threading.Thread(target=self._befehl_ausfuehren, args=(befehl,), daemon=True).start()

    def _befehl_ausfuehren(self, befehl):
        name = befehl['befehl']
        von = str(befehl.get('von', 'Leitzentrale'))[:40]
        self._ereignis(f'MQTT: {name.upper()} von {von}', 'stopp' if name == 'stopp' else 'info')
        daten = {'wert': befehl['wert']} if 'wert' in befehl else {}
        anfrage = urllib.request.Request(f'{self.panel_url}/api/{name}', data=json.dumps(daten).encode(),
                                         headers={'Content-Type': 'application/json'}, method='POST')
        try:
            with urllib.request.urlopen(anfrage, timeout=15) as antwort:
                text = json.loads(antwort.read() or b'{}').get('antwort', '')
            ok = not str(text).startswith(('Fehler', 'Laeuft schon', 'Es laeuft schon', 'Linienfolger hat sich'))
        except Exception as exc:
            text, ok = f'Panel nicht erreichbar ({exc})', False
            if name == 'stopp':
                self.cmd_pub.publish(Twist())
                text += '; Stillstand direkt an /cmd_vel gesendet'
        self._befehl_antwort({'id': befehl.get('id'), 'befehl': name, 'ok': ok, 'antwort': text})

    def _befehl_antwort(self, inhalt):
        inhalt.update(schema_version='1.0', robot_id=self.robot, boot_id=self.boot_id, generated_at=utc_now())
        self._enqueue(self._topic('cmd/result'), dumps(inhalt), 1, False)

    def _ereignis(self, text, art):
        self.ereignis_pub.publish(String(data=json.dumps({'zeit': time.time(), 'text': text, 'art': art})))

    def _load_subscriptions(self):
        for entry in self.config.get('subscriptions', []):
            try:
                topic = entry['ros_topic']
                msg_type = get_message(entry['ros_type'])
                qos = int(entry.get('qos', 0))
                callback = lambda msg, entry=entry: self._message(entry, msg)
                qos_profile = qos_profile_sensor_data if qos == 0 else 10
                self.ros_abos[topic] = self.create_subscription(msg_type, topic, callback, qos_profile)
            except Exception as exc:
                self.get_logger().error(f'ROS-Abo fuer {entry.get("ros_topic", "?")} fehlgeschlagen: {exc}')

    def _message(self, entry, message):
        self.seq += 1
        try:
            payload = message_to_ordereddict(message)
            if isinstance(message, String):
                try:
                    payload = json.loads(message.data)
                except (TypeError, ValueError):
                    payload = {'data': message.data}
            envelope = {'schema_version': '1.0', 'robot_id': self.robot, 'boot_id': self.boot_id,
                        'seq': self.seq, 'generated_at': utc_now(), 'ros_topic': entry['ros_topic'],
                        'ros_type': entry['ros_type'], 'payload': payload}
            encoded = dumps(envelope)
            if len(encoded.encode('utf-8')) > self.max_payload:
                self.get_logger().warn(f"MQTT-Nachricht verworfen (zu gross): {entry['ros_topic']}",
                                        throttle_duration_sec=30)
                return
            self._enqueue(self._topic(entry['mqtt_suffix']), encoded, int(entry.get('qos', 0)),
                          bool(entry.get('retain', False)))
        except Exception as exc:
            self.publish_errors += 1
            self.get_logger().error(f'MQTT-Serialisierung fehlgeschlagen: {exc}')

    def _enqueue(self, topic, payload, qos, retain):
        item = (topic, payload, qos, retain)
        try:
            self.queue.put_nowait(item)
        except queue.Full:
            try:
                self.queue.get_nowait()
                self.queue.put_nowait(item)
            except queue.Empty:
                pass

    def _publish_loop(self):
        while self.running:
            try:
                topic, payload, qos, retain = self.queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if self.mqtt_client is None:
                continue
            try:
                result = self.mqtt_client.publish(topic, payload, qos=qos, retain=retain)
                if result.rc != mqtt.MQTT_ERR_SUCCESS:
                    self.publish_errors += 1
            except Exception:
                self.publish_errors += 1

    def _status(self):
        status = {'schema_version': '1.0', 'robot_id': self.robot, 'boot_id': self.boot_id,
                  'connected': self.mqtt_connected, 'queued': self.queue.qsize(),
                  'publish_errors': self.publish_errors, 'zeit': utc_now(),
                  'befehle_angenommen': self.befehle_angenommen, 'befehle_abgelehnt': self.befehle_abgelehnt}
        self.status_pub.publish(String(data=dumps(status)))
        if self.mqtt_connected:
            self._enqueue(self._topic('state/bridge'), dumps(dict(status, generated_at=status['zeit'])), 0, True)

    def _publish_maps(self):
        """Verteilt Kartenindex und geaenderte Kartendateien, ohne ROS-Callbacks zu blockieren."""
        maps = self.config.get('maps', {})
        root = Path(maps.get('directory', 'karten'))
        if not root.is_absolute():
            root = REPO / root
        if not root.is_dir():
            return
        files = maps.get('files', ['karte.json', 'karte.png', 'karte.ply', 'karte.npz', 'wolke.bin'])
        chunk_size = int(maps.get('chunk_bytes', 200000))
        index = []
        for folder in sorted((path for path in root.iterdir() if path.is_dir())):
            eintrag = {'name': folder.name, 'files': {}}
            for name in files:
                datei = folder / name
                if not datei.is_file():
                    continue
                stat = datei.stat()
                signatur = (stat.st_mtime_ns, stat.st_size)
                schluessel = (folder.name, name)
                eintrag['files'][name] = {'bytes': stat.st_size, 'modified': stat.st_mtime,
                                          'chunks': max(1, (stat.st_size + chunk_size - 1) // chunk_size),
                                          'sha256': self.map_hashes.get(schluessel)}
                if self.map_signatures.get(schluessel) != signatur:
                    digest = hashlib.sha256()
                    with datei.open('rb') as stream:
                        nummer = 0
                        while True:
                            block = stream.read(chunk_size)
                            if not block:
                                break
                            digest.update(block)
                            suffix = f'files/{name}/{nummer:06d}'
                            self._enqueue(self._topic(f'maps/{folder.name}/{suffix}'), block, 1, True)
                            nummer += 1
                    self.map_signatures[schluessel] = signatur
                    self.map_hashes[schluessel] = digest.hexdigest()
                    eintrag['files'][name]['sha256'] = self.map_hashes[schluessel]
            index.append(eintrag)
        payload = {'schema_version': '1.0', 'robot_id': self.robot, 'boot_id': self.boot_id,
                   'generated_at': utc_now(), 'maps': index,
                   'file_topic_pattern': self._topic('maps/<name>/files/<file>/<chunk>')}
        self._enqueue(self._topic('maps/index'), dumps(payload), 1, True)

    def close(self):
        self.running = False
        if self.mqtt_client is not None:
            try:
                self.mqtt_client.publish(self._topic('availability'), 'offline', qos=1, retain=True)
                self.mqtt_client.loop_stop()
                self.mqtt_client.disconnect()
            except Exception:
                pass


def main():
    parser = argparse.ArgumentParser(description='ROS2-Nachrichten an MQTT senden')
    parser.add_argument('--config', default=os.path.join(os.path.dirname(__file__), 'config.yaml'))
    args = parser.parse_args()
    rclpy.init()
    node = MqttBridge(load_config(args.config))
    signal.signal(signal.SIGINT, lambda *_: rclpy.shutdown())
    signal.signal(signal.SIGTERM, lambda *_: rclpy.shutdown())
    try:
        rclpy.spin(node)
    finally:
        node.close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
