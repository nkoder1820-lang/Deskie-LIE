"""Small persisted key-value store for settings togglable from the UI.

Env vars in .env remain the defaults; anything set here (via PATCH
/api/settings) overrides them and survives restarts. Stored as a JSON file
next to the SQLite DB — no migration, human-readable, gitignored.
"""
import json
import logging
import os
import threading

logger = logging.getLogger(__name__)

_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "runtime_settings.json"))
_lock = threading.Lock()


def _load() -> dict:
    try:
        with open(_PATH, encoding="utf-8") as f:
            return json.load(f) or {}
    except FileNotFoundError:
        return {}
    except Exception as e:  # noqa: BLE001
        logger.warning(f"runtime_settings.json unreadable ({e}) — using env defaults")
        return {}


def get(key: str, default=None):
    with _lock:
        return _load().get(key, default)


def set_value(key: str, value) -> None:
    with _lock:
        data = _load()
        data[key] = value
        with open(_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
