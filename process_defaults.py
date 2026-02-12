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

# UI Sizing / Layout
# Baseline design target is the Raspberry Pi Official 7" DSI (800×480).
# The UI code scales fonts/padding relative to these values so other
# screen sizes can be supported by changing only these settings.
UI_BASE_WIDTH = 800
UI_BASE_HEIGHT = 480

# Default window behaviour.
# - On Raspberry Pi, the UI uses fullscreen by default.
# - On non-Pi (dev), the UI uses a fixed-size window for predictable layout.
UI_FULLSCREEN_ON_PI = True
UI_WINDOWED_GEOMETRY = "800x480"

# Clamp scaling to avoid extreme sizes on unusual displays.
UI_SCALE_MIN = 0.85
UI_SCALE_MAX = 1.40
