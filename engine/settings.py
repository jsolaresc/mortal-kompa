"""
settings.py
------------
Configuración persistente simple: volumen por categoría y pantalla
completa. Se guarda en data/settings.json (se crea solo la primera vez).
"""

import json
import os

from engine import constants as C

DEFAULTS = {
    "music_volume": 0.6,
    "stage_music_volume": 0.6,
    "sfx_volume": 1.0,
    "announcer_volume": 1.0,
    "fullscreen": False,
    "resolution": C.DEFAULT_RESOLUTION,
    "touch_scale": 1.0,  # tamaño de los botones táctiles (Android)
}


def load_settings():
    if os.path.isfile(C.SETTINGS_PATH):
        try:
            with open(C.SETTINGS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            merged = dict(DEFAULTS)
            merged.update(data)
            return merged
        except (json.JSONDecodeError, OSError):
            pass
    return dict(DEFAULTS)


def save_settings(settings):
    os.makedirs(os.path.dirname(C.SETTINGS_PATH), exist_ok=True)
    with open(C.SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
