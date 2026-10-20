#!/usr/bin/env python3
# Prueft die MQTT-Bridge in beide Richtungen (Roboter -> Broker und Broker -> Roboter), ohne Roboter und ohne ROS.
# Aufruf:  python3 tests/test_mqtt.py
# Teil 1 (Befehlspruefung) braucht nur PyYAML. Teil 2 startet einen lokalen Test-Broker und braucht
# paho-mqtt und amqtt:  python3 -m pip install --user paho-mqtt amqtt   (sonst wird Teil 2 uebersprungen)
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HIER, 'attrappen'))
sys.path.insert(0, os.path.join(HIER, '..', 'mqtt'))
from common import befehl_pruefen  # noqa: E402

ergebnisse = []


def pruefe(text, ok):
    print(f"{'OK  ' if ok else 'FEHLER'} {text}")
    ergebnisse.append(bool(ok))


def teil_befehle():
    erlaubt = {'stopp', 'test', 'tempo'}
    jetzt = 1000.0
    b, f = befehl_pruefen(b'stopp', False, erlaubt, 10, jetzt)
    pruefe('STOPP als einfacher Text', b and b['befehl'] == 'stopp' and f is None)
    b, f = befehl_pruefen(b'{"befehl": "STOPP", "gesendet": 1}', False, set(), 10, jetzt)
    pruefe('STOPP immer erlaubt, auch alt und ohne Freigabe', b is not None)
    b, f = befehl_pruefen(b'{"befehl": "test"}', True, erlaubt, 10, jetzt)
    pruefe('Retained-Befehl wird ignoriert', b is None and 'Retained' in f)
    b, f = befehl_pruefen(b'{"befehl": "start"}', False, erlaubt, 10, jetzt)
    pruefe('START ohne Freigabe abgelehnt', b is None and 'nicht freigegeben' in f)
    b, f = befehl_pruefen(b'{"befehl": "test", "gesendet": 980}', False, erlaubt, 10, jetzt)
    pruefe('Zu alter TEST-Befehl abgelehnt', b is None and 'zu alt' in f)
    b, f = befehl_pruefen(b'{"befehl": "tempo", "wert": "0.2"}', False, erlaubt, 10, jetzt)
    pruefe('Tempo mit Wert', b and b['wert'] == 0.2)
    b, f = befehl_pruefen(b'{"befehl": "tempo"}', False, erlaubt, 10, jetzt)
    pruefe('Tempo ohne Wert abgelehnt', b is None)
    b, f = befehl_pruefen(b'{"befehl": "rm -rf"}', False, erlaubt, 10, jetzt)
    pruefe('Unbekannter Befehl abgelehnt', b is None and 'Unbekannt' in f)
    b, f = befehl_pruefen(b'\xff\xfe', False, erlaubt, 10, jetzt)
    pruefe('Kaputte Nutzdaten abgelehnt', b is None)


def freier_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def warte(bedingung, sekunden=5.0):
    ende = time.time() + sekunden
    while time.time() < ende:
        if bedingung():
            return True
        time.sleep(0.05)
    return False


def teil_broker():
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        print('-- Teil 2 uebersprungen: paho-mqtt fehlt')
        return
    if shutil.which('amqtt') is None:
        print('-- Teil 2 uebersprungen: amqtt (Test-Broker) fehlt')
        return
    # rosidl_runtime_py gibt es ohne ROS nicht: kleine Attrappe fuer die Bridge
    konv = types.ModuleType('rosidl_runtime_py.convert')
    konv.message_to_ordereddict = lambda m: dict(vars(m))
    util = types.ModuleType('rosidl_runtime_py.utilities')
    util.get_message = lambda name: __import__('std_msgs.msg', fromlist=['String']).String
    sys.modules.update({'rosidl_runtime_py': types.ModuleType('rosidl_runtime_py'),
                        'rosidl_runtime_py.convert': konv, 'rosidl_runtime_py.utilities': util})
    import bridge
    from common import mqtt_client
    from std_msgs.msg import String

    mqtt_port, panel_port = freier_port(), freier_port()
    ordner = tempfile.mkdtemp()
    with open(os.path.join(ordner, 'broker.yaml'), 'w') as f:
        f.write(f"listeners:\n  default:\n    type: tcp\n    bind: 127.0.0.1:{mqtt_port}\n"
                "plugins:\n  amqtt.plugins.authentication.AnonymousAuthPlugin:\n    allow_anonymous: true\n")
    broker = subprocess.Popen(['amqtt', '-c', os.path.join(ordner, 'broker.yaml')],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Attrappe der Panel-API: merkt sich, welche Aktionen ankommen
    panel_aufrufe = []

    class Panel(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            daten = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
            panel_aufrufe.append((self.path, daten))
            antwort = {'/api/stopp': 'Gestoppt', '/api/test': 'Testmodus: zeigt alles, faehrt nicht.'}
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps({'antwort': antwort.get(self.path, 'Tempo 0.20 m/s')}).encode())

    panel = ThreadingHTTPServer(('127.0.0.1', panel_port), Panel)
    threading.Thread(target=panel.serve_forever, daemon=True).start()

    try:
        warte(lambda: socket.socket().connect_ex(('127.0.0.1', mqtt_port)) == 0)
        config = {'broker': {'host': '127.0.0.1', 'port': mqtt_port, 'keepalive': 10}, 'robot_id': 'RMTEST',
                  'base_topic': 'smartcity/robots', 'maps': {'directory': ordner},
                  'subscriptions': [{'ros_topic': '/ki/befehl', 'ros_type': 'std_msgs/msg/String',
                                     'mqtt_suffix': 'state/ki_befehl', 'qos': 1, 'retain': True}],
                  'commands': {'allowed': ['stopp', 'test', 'tempo'], 'max_age_seconds': 10,
                               'panel_url': f'http://127.0.0.1:{panel_port}'}}
        knoten = bridge.MqttBridge(config)
        pruefe('Bridge verbindet mit dem Broker', warte(lambda: knoten.mqtt_connected))

        empfangen = []
        leser = mqtt_client(mqtt, 'test-leser', config['broker'])
        leser.on_message = lambda c, u, m: empfangen.append((m.topic, m.payload, m.retain))
        leser.connect('127.0.0.1', mqtt_port)
        leser.subscribe('smartcity/robots/RMTEST/#', qos=1)
        leser.loop_start()

        def nachrichten(suffix):
            return [json.loads(p) if p[:1] in (b'{', b'[') else p.decode() for t, p, r in list(empfangen)
                    if t == 'smartcity/robots/RMTEST/' + suffix]

        pruefe('Verfuegbarkeit "online" am Broker', warte(lambda: 'online' in nachrichten('availability')))
        pruefe('Info nennt die freigegebenen Befehle',
               warte(lambda: any('test' in i.get('befehle', []) for i in nachrichten('info'))))

        # Roboter -> Broker
        knoten._message(config['subscriptions'][0], String(data=json.dumps({'aktion': 'fahren', 'grund': 'frei'})))
        pruefe('ROS-Status kommt als JSON-Huelle am Broker an', warte(lambda: any(
            n['payload'] == {'aktion': 'fahren', 'grund': 'frei'} and n['robot_id'] == 'RMTEST'
            for n in nachrichten('state/ki_befehl'))))
        knoten._status()
        pruefe('Bridge-Status unter state/bridge', warte(lambda: any(
            n.get('connected') for n in nachrichten('state/bridge'))))

        # Broker -> Roboter
        sender = mqtt_client(mqtt, 'test-leitzentrale', config['broker'])
        sender.connect('127.0.0.1', mqtt_port)
        sender.loop_start()
        cmd_vel = knoten.pubs['/cmd_vel']
        sender.publish('smartcity/robots/RMTEST/cmd', json.dumps({'id': 'a1', 'befehl': 'stopp', 'von': 'Test'}), qos=1)
        pruefe('STOPP erreicht die Panel-API', warte(lambda: ('/api/stopp', {}) in panel_aufrufe))
        pruefe('STOPP sendet sofort Stillstand an /cmd_vel', cmd_vel.n >= 1)
        pruefe('Antwort auf STOPP unter cmd/result', warte(lambda: any(
            n.get('id') == 'a1' and n['ok'] for n in nachrichten('cmd/result'))))
        pruefe('STOPP-Ereignis fuer das Panel', knoten.pubs['/ki/ereignis'].n >= 1)

        sender.publish('smartcity/robots/all/cmd', json.dumps({'id': 'a2', 'befehl': 'tempo', 'wert': 0.2,
                                                               'gesendet': time.time()}), qos=1)
        pruefe('Tempo ueber all/cmd erreicht die Panel-API',
               warte(lambda: ('/api/tempo', {'wert': 0.2}) in panel_aufrufe))

        sender.publish('smartcity/robots/RMTEST/cmd', json.dumps({'id': 'a3', 'befehl': 'start'}), qos=1)
        pruefe('START wird abgelehnt und beantwortet', warte(lambda: any(
            n.get('id') == 'a3' and not n['ok'] for n in nachrichten('cmd/result'))))
        pruefe('START erreicht das Panel nicht', not any(p == '/api/start' for p, _ in panel_aufrufe))

        sender.publish('smartcity/robots/RMTEST/cmd', json.dumps({'befehl': 'test'}), qos=1, retain=True)
        time.sleep(0.5)
        anzahl = len(panel_aufrufe)
        knoten.mqtt_client.reconnect()          # Neuverbinden: Broker liefert den retained Befehl nach
        warte(lambda: knoten.mqtt_connected)
        time.sleep(1.0)
        pruefe('Retained-Befehl wird nach Neuverbinden nicht ausgefuehrt',
               not any(p == '/api/test' for p, _ in panel_aufrufe[anzahl:]))

        sender.publish('smartcity/robots/RMTEST/cmd', json.dumps({'id': 'a4', 'befehl': 'test'}), qos=1)
        sender.publish('smartcity/robots/RMTEST/cmd', json.dumps({'id': 'a4', 'befehl': 'test'}), qos=1)
        warte(lambda: any(p == '/api/test' for p, _ in panel_aufrufe[anzahl:]))
        time.sleep(0.5)
        pruefe('Doppelte Befehls-ID wird nur einmal ausgefuehrt',
               sum(p == '/api/test' for p, _ in panel_aufrufe[anzahl:]) == 1)

        panel.shutdown()
        panel.server_close()
        sender.publish('smartcity/robots/RMTEST/cmd', json.dumps({'id': 'a5', 'befehl': 'stopp'}), qos=1)
        pruefe('STOPP ohne Panel: Stillstand trotzdem gesendet', warte(lambda: any(
            n.get('id') == 'a5' and not n['ok'] and 'cmd_vel' in n['antwort'] for n in nachrichten('cmd/result')),
            20))

        knoten.close()
        sender.loop_stop()
        leser.loop_stop()
    finally:
        broker.terminate()
        broker.wait(5)
        shutil.rmtree(ordner, ignore_errors=True)


def main():
    teil_befehle()
    teil_broker()
    print()
    if all(ergebnisse):
        print('Alle Tests bestanden.')
        return 0
    print(f'{ergebnisse.count(False)} Test(s) fehlgeschlagen.')
    return 1


if __name__ == '__main__':
    sys.exit(main())
