"""config.py — Backward-compatible configuration facade.

This file remains as the single import target (`import config as CFG`) so
existing modules do not need to change their import style.

Configuration is split into:
	- calibration.py      (wiring, calibration constants, geometry)
	- process_defaults.py (process behavior, UI timings, UI look)
"""

# Re-export everything so callers can continue to use CFG.X
from calibration import *  # noqa: F403
from process_defaults import *  # noqa: F403
