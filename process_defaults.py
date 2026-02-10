"""process_defaults.py — Brew process defaults and UI timing.

This module holds values that are more about how you want the system to run
(stir schedule, brew duration limits, save intervals, UI refresh) rather than
hardware wiring.
"""

# Brew Defaults
DEFAULT_DILUTION_RATIO   = 10.0   # lb water per lb fertilizer
WATER_DENSITY_LB_PER_GAL = 8.34   # ≈ lb per US gallon of water

# Stirring schedule
STIR_ON_SECONDS    = 5 * 60     # 5 minutes on
STIR_CYCLE_SECONDS = 30 * 60    # every 30 minutes

# Brew duration limits (hours)
BREW_MIN_HOURS = 1
BREW_MAX_HOURS = 36

# State persistence / UI refresh
STATE_SAVE_INTERVAL_SEC = 60
UI_REFRESH_INTERVAL_MS  = 1000

# Temperature polling suggestion (controller/UI may cache)
TEMP_READ_INTERVAL_SEC = 5
TEMP_INVALID_THRESHOLD = -20.0

# UI Appearance
UI_FONT_FAMILY = "Helvetica"
UI_BG_COLOR    = "#1e1e2e"
UI_FG_COLOR    = "#cdd6f4"
UI_ACCENT      = "#89b4fa"
UI_WARN        = "#f38ba8"
UI_OK          = "#a6e3a1"
UI_BUTTON_BG   = "#313244"
UI_ENTRY_BG    = "#45475a"
