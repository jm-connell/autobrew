"""
state_manager.py — Persistent state for power-loss recovery.

Saves the current brew state to a JSON file periodically.  On startup the
controller checks for an existing state file and offers to resume.
"""

import json
import logging
from pathlib import Path

import config as CFG

log = logging.getLogger("autobrew.state")


# ──────────────────────────────────────────────────────────────────────
# State data structure  (plain dict serialised to JSON)
# ──────────────────────────────────────────────────────────────────────
def new_state() -> dict:
    """Return a blank/default state dictionary."""
    return {
        "phase": "idle",               # idle | fill | brew | complete
        "fert_weight_lb": 0.0,
        "dilution_ratio": CFG.DEFAULT_DILUTION_RATIO,
        "target_gallons": 0.0,
        "added_gallons": 0.0,
        "brew_duration_sec": 0,
        "brew_elapsed_sec": 0.0,
        "brew_start_wallclock": None,   # ISO-8601 timestamp (informational)
        "skip_fill": False,
        "last_temp_f": None,
        "last_temp_c": None,
        "last_save_wallclock": None,
        "stir_cycle_elapsed_sec": 0.0,  # seconds into current 30-min stir cycle
    }


# ──────────────────────────────────────────────────────────────────────
# Save / Load
# ──────────────────────────────────────────────────────────────────────
def save_state(state: dict, path: Path = CFG.STATE_FILE) -> bool:
    """Write *state* to the JSON file.  Returns True on success."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w") as fh:
            json.dump(state, fh, indent=2)
        # Atomic-ish rename (safe against partial writes on power loss)
        tmp.replace(path)
        log.debug("State saved → %s", path)
        return True
    except Exception as exc:
        log.error("Failed to save state: %s", exc)
        return False


def load_state(path: Path = CFG.STATE_FILE) -> dict | None:
    """
    Load state from disk.  Returns the dict, or *None* if the file does
    not exist or is corrupt (in which case the file is removed).
    """
    if not path.exists():
        return None
    try:
        with open(path, "r") as fh:
            data = json.load(fh)
        log.info("State loaded from %s (phase=%s)", path, data.get("phase"))
        return data
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        log.error("Corrupt state file (%s) — removing: %s", path, exc)
        try:
            path.unlink()
        except OSError:
            pass
        return None


def clear_state(path: Path = CFG.STATE_FILE):
    """Delete the state file (cycle complete or user chose not to resume)."""
    try:
        if path.exists():
            path.unlink()
            log.info("State file removed")
    except OSError as exc:
        log.error("Could not remove state file: %s", exc)
