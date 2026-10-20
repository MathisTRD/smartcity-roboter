#!/usr/bin/env python3
"""Gemeinsame MQTT-Konfiguration und JSON-Serialisierung."""
import base64
import json
import os
import time
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

import yaml


def load_config(path):
    with open(path, encoding='utf-8') as datei:
        return yaml.safe_load(datei) or {}


def robot_id(config):
    value = os.environ.get('SMARTCITY_ROBOT_ID') or config.get('robot_id')
    if value:
        return str(value).strip()
    try:
        value = Path.home().joinpath('roboter_name').read_text(encoding='utf-8').strip()
        if value:
            return value
    except OSError:
        pass
    return 'UNBEKANNT'


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def env_value(config, key):
    name = config.get(key + '_env')
    return os.environ.get(name) if name else config.get(key)


def jsonable(value):
    if isinstance(value, (bytes, bytearray)):
        return {'base64': base64.b64encode(value).decode('ascii')}
    if isinstance(value, (OrderedDict, dict)):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if hasattr(value, 'item'):
        return jsonable(value.item())
    return value


def dumps(value):
    return json.dumps(jsonable(value), ensure_ascii=True, separators=(',', ':'), allow_nan=False)


def mqtt_client(mqtt, client_id, broker):
    """Client fuer paho-mqtt 1.x und 2.x (2.x braucht die Angabe der Callback-Version)."""
    if hasattr(mqtt, 'CallbackAPIVersion'):
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id=client_id, clean_session=True)
    else:
        client = mqtt.Client(client_id=client_id, clean_session=True)
    username = env_value(broker, 'username')
    if username:
        client.username_pw_set(username, env_value(broker, 'password'))
    if broker.get('tls'):
        client.tls_set()
    return client


# Befehle, die ueber MQTT an einen Roboter gehen duerfen. Alles andere wird abgelehnt.
BEFEHLE = ('stopp', 'test', 'start', 'tempo')


def befehl_pruefen(roh, retained, erlaubt, max_alter, jetzt=None):
    """Prueft einen MQTT-Befehl. Rueckgabe (befehl, fehler); genau eines davon ist None.

    roh: Nutzdaten als bytes, entweder JSON {"befehl": "stopp", "id": ..., "wert": ..., "gesendet": <unix>}
    oder nur der Befehlsname. Retained-Befehle werden nie ausgefuehrt (sonst faehrt der Roboter nach
    jedem Neuverbinden los). STOPP ist immer erlaubt und darf auch alt sein.
    """
    try:
        text = roh.decode('utf-8').strip()
    except (AttributeError, UnicodeDecodeError):
        return None, 'Befehl ist kein Text'
    try:
        befehl = json.loads(text)
    except ValueError:
        befehl = {'befehl': text}
    if not isinstance(befehl, dict):
        befehl = {'befehl': str(befehl)}
    name = str(befehl.get('befehl', '')).strip().lower()
    befehl['befehl'] = name
    if retained:
        return None, 'Retained-Befehl ignoriert'
    if name not in BEFEHLE:
        return None, f'Unbekannter Befehl: {name or "?"}'
    if name != 'stopp' and name not in erlaubt:
        return None, f'Befehl "{name}" ist ueber MQTT nicht freigegeben (mqtt/config.yaml -> commands.allowed)'
    gesendet = befehl.get('gesendet')
    if name != 'stopp' and gesendet is not None:
        try:
            alter = (time.time() if jetzt is None else jetzt) - float(gesendet)
        except (TypeError, ValueError):
            return None, 'Feld "gesendet" ist keine Zahl'
        if alter > max_alter:
            return None, f'Befehl zu alt ({alter:.0f} s)'
    if name == 'tempo':
        try:
            befehl['wert'] = float(befehl.get('wert'))
        except (TypeError, ValueError):
            return None, 'Tempo braucht "wert" in m/s'
    return befehl, None
