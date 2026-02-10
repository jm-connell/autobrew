"""
config.py — Constants and configuration for the AutoBrew fertilizer brewing system.

All GPIO pin assignments, calibration values, tank geometry, and default
brew parameters live here so they can be tuned in one place.
"""

from pathlib import Path

# ──────────────────────────────────────────────────────────────────────
# GPIO Pin Assignments  (BCM numbering)
# ──────────────────────────────────────────────────────────────────────
# DS18B20 1-Wire temperature probe (handled by w1thermsensor, uses GPIO 4
# by default — enabled via raspi-config or dtoverlay=w1-gpio in config.txt).
GPIO_DS18B20 = 4  # informational; w1thermsensor auto-detects

# Relay outputs (accent HIGH = relay energised → device ON)
GPIO_RELAY_SOLENOID = 17   # 12 V solenoid valve for water fill
GPIO_RELAY_PADDLE   = 27   # AC mixing paddle motor

# Ultrasonic level sensor JSN-SR04T
GPIO_ULTRA_TRIGGER = 23
GPIO_ULTRA_ECHO    = 24

# DIGITEN FL-608 Hall-effect flow meter (pulse → GPIO via voltage divider)
GPIO_FLOW_METER = 25

# ──────────────────────────────────────────────────────────────────────
# Flow Meter Calibration
# ──────────────────────────────────────────────────────────────────────
# The FL-608 spec: ~450 pulses / litre  →  ~1703 pulses / US gallon.
# Adjust after real-world calibration with a known volume.
FLOW_PULSES_PER_GALLON = 1703

# ──────────────────────────────────────────────────────────────────────
# Tank Geometry  (used by ultrasonic level sensor)
# ──────────────────────────────────────────────────────────────────────
# Distances are measured from the sensor face (mounted at the top of the
# tank, pointing down) to the water surface.
TANK_CAPACITY_GALLONS   = 500    # max working capacity
TANK_HEIGHT_CM          = 120.0  # sensor-to-bottom distance (cm)
TANK_EMPTY_DISTANCE_CM  = 118.0  # reading when tank is empty
TANK_FULL_DISTANCE_CM   = 10.0   # reading when tank is full

# Safety: stop fill if level exceeds this percentage
TANK_OVERFILL_PCT = 95.0

# ──────────────────────────────────────────────────────────────────────
# Brew Defaults
# ──────────────────────────────────────────────────────────────────────
DEFAULT_DILUTION_RATIO  = 10.0   # lb water per lb fertilizer
WATER_DENSITY_LB_PER_GAL = 8.34  # ≈ lb per US gallon at room temp

# Stirring schedule
STIR_ON_SECONDS  = 5 * 60   # 5 minutes on
STIR_CYCLE_SECONDS = 30 * 60  # every 30 minutes

# Brew duration limits (hours)
BREW_MIN_HOURS = 1
BREW_MAX_HOURS = 36

# ──────────────────────────────────────────────────────────────────────
# State Persistence
# ──────────────────────────────────────────────────────────────────────
STATE_DIR  = Path("/home/pi/brewer-controller")
STATE_FILE = STATE_DIR / "brew_state.json"
LOG_FILE   = STATE_DIR / "autobrew.log"

# How often (seconds) to auto-save state & refresh the UI
STATE_SAVE_INTERVAL_SEC = 60
UI_REFRESH_INTERVAL_MS  = 1000   # 1 second

# ──────────────────────────────────────────────────────────────────────
# Temperature
# ──────────────────────────────────────────────────────────────────────
TEMP_READ_INTERVAL_SEC = 5  # seconds between DS18B20 reads
TEMP_INVALID_THRESHOLD = -20.0  # readings below this → sensor error

# ──────────────────────────────────────────────────────────────────────
# Relay active-high vs active-low
# ──────────────────────────────────────────────────────────────────────
# Most relay HATs for Pi are active-low (relay closes when GPIO is LOW).
# Set to True if your relay module energises on LOW.
RELAY_ACTIVE_LOW = True

# ──────────────────────────────────────────────────────────────────────
# UI Appearance
# ──────────────────────────────────────────────────────────────────────
UI_FONT_FAMILY = "Helvetica"
UI_BG_COLOR    = "#1e1e2e"
UI_FG_COLOR    = "#cdd6f4"
UI_ACCENT      = "#89b4fa"
UI_WARN        = "#f38ba8"
UI_OK          = "#a6e3a1"
UI_BUTTON_BG   = "#313244"
UI_ENTRY_BG    = "#45475a"
