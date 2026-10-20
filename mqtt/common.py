#!/usr/bin/env python3
"""Gemeinsame MQTT-Konfiguration und JSON-Serialisierung."""
import base64
import json
import os
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
