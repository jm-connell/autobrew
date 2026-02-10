"""config.py — Backward-compatible configuration facade.

This file remains as the single import target (`import config as CFG`) so
existing modules do not need to change their import style.

Configuration is split into:
	- calibration.py      (wiring, calibration constants, geometry)
	- process_defaults.py (process behavior, UI timings, UI look)
"""

# NOTE: This module is intentionally the single import target used
# throughout the codebase (`import config as CFG`).
#
# It loads persistent calibration settings (settings.json) at import time
# and exposes an `apply_runtime_settings()` helper for the calibration UI.

from __future__ import annotations

import json
import logging
from pathlib import Path

import calibration as _CAL

# Re-export everything so callers can continue to use CFG.X
from calibration import *  # noqa: F403
from process_defaults import *  # noqa: F403

log = logging.getLogger("autobrew.config")


SETTINGS_FILE: Path = _CAL.STATE_DIR / "settings.json"

# Set after loading settings (used by UI to decide whether to show wizard)
CALIBRATION_COMPLETE: bool = False


def apply_runtime_settings(settings: dict):
	"""Apply settings dict to this module's globals at runtime."""
	global CALIBRATION_COMPLETE

	if not isinstance(settings, dict):
		return

	# Flow
	if "flow_pulses_per_gallon" in settings:
		globals()["FLOW_PULSES_PER_GALLON"] = int(settings["flow_pulses_per_gallon"])

	# Tank
	if "tank_capacity_gallons" in settings:
		globals()["TANK_CAPACITY_GALLONS"] = float(settings["tank_capacity_gallons"])
	if "tank_empty_distance_cm" in settings:
		globals()["TANK_EMPTY_DISTANCE_CM"] = float(settings["tank_empty_distance_cm"])
	if "tank_full_distance_cm" in settings:
		globals()["TANK_FULL_DISTANCE_CM"] = float(settings["tank_full_distance_cm"])
	if "tank_overfill_pct" in settings:
		globals()["TANK_OVERFILL_PCT"] = float(settings["tank_overfill_pct"])
	if "level_sensor_failsafe_stop" in settings:
		globals()["LEVEL_SENSOR_FAILSAFE_STOP"] = bool(settings["level_sensor_failsafe_stop"])

	# Relay polarity
	if "relay_active_low" in settings:
		globals()["RELAY_ACTIVE_LOW"] = bool(settings["relay_active_low"])

	CALIBRATION_COMPLETE = bool(settings.get("calibration_complete", False))


def _load_settings_file(path: Path) -> dict | None:
	if not path.exists():
		return None
	try:
		with open(path, "r", encoding="utf-8") as fh:
			data = json.load(fh)
		return data if isinstance(data, dict) else None
	except Exception as exc:
		log.error("Failed to load settings file %s: %s", path, exc)
		return None


_settings = _load_settings_file(SETTINGS_FILE)
if _settings:
	apply_runtime_settings(_settings)
