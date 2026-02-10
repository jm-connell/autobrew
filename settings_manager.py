"""settings_manager.py — Persistent calibration & setup settings.

This stores calibration values that vary between units and over time
(e.g., flow-meter pulses/gal, ultrasonic empty/full distances).

Stored as JSON in the same directory as the state file.
"""

from __future__ import annotations

import json
import logging
import datetime
from pathlib import Path

import calibration as CAL

log = logging.getLogger("autobrew.settings")

SETTINGS_FILE: Path = CAL.STATE_DIR / "settings.json"


def default_settings() -> dict:
    return {
        "settings_version": 1,
        "calibration_complete": False,
        "calibrated_at": None,
        # Flow
        "flow_pulses_per_gallon": CAL.FLOW_PULSES_PER_GALLON,
        # Tank / ultrasonic
        "tank_capacity_gallons": CAL.TANK_CAPACITY_GALLONS,
        "tank_empty_distance_cm": CAL.TANK_EMPTY_DISTANCE_CM,
        "tank_full_distance_cm": CAL.TANK_FULL_DISTANCE_CM,
        "tank_overfill_pct": CAL.TANK_OVERFILL_PCT,
        "level_sensor_failsafe_stop": CAL.LEVEL_SENSOR_FAILSAFE_STOP,
        # Relay polarity
        "relay_active_low": CAL.RELAY_ACTIVE_LOW,
    }


def load_settings(path: Path = SETTINGS_FILE) -> dict | None:
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return None
        return data
    except json.JSONDecodeError as exc:
        log.error("Corrupt settings file %s: %s", path, exc)
        return None
    except OSError as exc:
        log.error("Could not read settings file %s: %s", path, exc)
        return None


def save_settings(settings: dict, path: Path = SETTINGS_FILE) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")

        # Stamp calibration timestamp if marked complete
        if settings.get("calibration_complete") and not settings.get("calibrated_at"):
            settings["calibrated_at"] = datetime.datetime.now().isoformat()

        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(settings, fh, indent=2)
        tmp.replace(path)
        log.info("Settings saved → %s", path)
        return True
    except OSError as exc:
        log.error("Could not write settings file %s: %s", path, exc)
        return False


def merge_with_defaults(settings: dict | None) -> dict:
    """Ensure all expected keys exist, without overwriting provided values."""
    merged = default_settings()
    if isinstance(settings, dict):
        merged.update(settings)
    return merged
