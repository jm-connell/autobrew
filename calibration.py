"""calibration.py — Hardware pins, calibration constants, and tank geometry.

This module is intended to hold values that are set by wiring and
real-world calibration (flow meter pulse constant, ultrasonic geometry,
relay polarity, etc.).
"""

from pathlib import Path

# ──────────────────────────────────────────────────────────────────────
# GPIO Pin Assignments  (BCM numbering)
# ──────────────────────────────────────────────────────────────────────
GPIO_DS18B20 = 4  # informational; w1thermsensor auto-detects

GPIO_RELAY_SOLENOID = 17   # 12 V solenoid valve
GPIO_RELAY_PADDLE   = 27   # AC mixing paddle

GPIO_ULTRA_TRIGGER = 23
GPIO_ULTRA_ECHO    = 24

GPIO_FLOW_METER = 25

# ──────────────────────────────────────────────────────────────────────
# Flow Meter Calibration
# ──────────────────────────────────────────────────────────────────────
# The FL-608 spec: ~450 pulses / litre  →  ~1703 pulses / US gallon.
# Adjust after real-world calibration with a known volume.
FLOW_PULSES_PER_GALLON = 1703

# ──────────────────────────────────────────────────────────────────────
# Tank Geometry (Ultrasonic)
# ──────────────────────────────────────────────────────────────────────
TANK_CAPACITY_GALLONS   = 500
TANK_HEIGHT_CM          = 120.0
TANK_EMPTY_DISTANCE_CM  = 118.0
TANK_FULL_DISTANCE_CM   = 10.0

# Safety: stop fill if level exceeds this percentage
TANK_OVERFILL_PCT = 95.0

# If True: if the level sensor cannot be read during FILL, stop filling.
LEVEL_SENSOR_FAILSAFE_STOP = True

# ──────────────────────────────────────────────────────────────────────
# Relay polarity
# ──────────────────────────────────────────────────────────────────────
# Most relay HATs for Pi are active-low (relay energises when GPIO is LOW).
RELAY_ACTIVE_LOW = True

# ──────────────────────────────────────────────────────────────────────
# Persistence paths
# ──────────────────────────────────────────────────────────────────────
STATE_DIR  = Path("/home/pi/brewer-controller")
STATE_FILE = STATE_DIR / "brew_state.json"
LOG_FILE   = STATE_DIR / "autobrew.log"
