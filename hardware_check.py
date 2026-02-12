"""hardware_check.py — Device detection registry for AutoBrew.

Defines every sensor and actuator the system needs and how to verify
each one is connected.  Adding or removing a device only requires
editing the DEVICE_REGISTRY list.
"""

from __future__ import annotations

import time
import logging
from dataclasses import dataclass
from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from hardware import HardwareManager

import config as CFG

log = logging.getLogger("autobrew.hardware_check")


# ──────────────────────────────────────────────────────────────────────
# Data classes
# ──────────────────────────────────────────────────────────────────────
@dataclass
class DeviceCheck:
    """Descriptor for one hardware device that the system needs.

    To add a new sensor or actuator, create a check function and append
    a ``DeviceCheck`` to ``DEVICE_REGISTRY`` below.
    """

    key: str                                        # unique identifier
    name: str                                       # human-friendly label
    description: str                                # what the device does
    check_fn: Callable[["HardwareManager"], bool]   # returns True → detected
    troubleshoot: str                               # wiring/connection guidance
    pins: str                                       # which GPIO pins / bus
    required: bool = True                           # False = optional peripheral


@dataclass
class CheckResult:
    """Result of running a single device check."""

    device: DeviceCheck
    detected: bool
    detail: str = ""                                # optional extra info


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────
def _is_on_pi() -> bool:
    from hardware import ON_PI
    return ON_PI


# ──────────────────────────────────────────────────────────────────────
# Individual check functions
# ──────────────────────────────────────────────────────────────────────
def _check_temp_probe(hw: "HardwareManager") -> bool:
    """DS18B20 is detected if w1thermsensor found a sensor on the bus."""
    return hw.temp._sensor is not None


def _check_solenoid_relay(hw: "HardwareManager") -> bool:
    """Relay GPIO device was created successfully (or running in mock mode)."""
    return hw.solenoid._device is not None or not _is_on_pi()


def _check_paddle_relay(hw: "HardwareManager") -> bool:
    return hw.paddle._device is not None or not _is_on_pi()


def _check_flow_meter(hw: "HardwareManager") -> bool:
    return hw.flow._device is not None or not _is_on_pi()


def _check_ultrasonic(hw: "HardwareManager") -> bool:
    """Try up to 3 distance reads; connected if any succeed."""
    if not _is_on_pi():
        return True
    if hw.level._trigger is None or hw.level._echo is None:
        return False
    for _ in range(3):
        if hw.level.read_distance_cm() is not None:
            return True
        time.sleep(0.05)
    return False


# ══════════════════════════════════════════════════════════════════════
#  Device Registry
#
#  To add a new device:   append a DeviceCheck entry.
#  To remove a device:    delete its entry.
#  Everything else (UI, check loop) adapts automatically.
# ══════════════════════════════════════════════════════════════════════
DEVICE_REGISTRY: list[DeviceCheck] = [
    DeviceCheck(
        key="temp_probe",
        name="Temperature Probe (DS18B20)",
        description="Monitors water temperature during the brew cycle.",
        check_fn=_check_temp_probe,
        troubleshoot=(
            f"Connect the DS18B20 data line to GPIO {CFG.GPIO_DS18B20} (BCM) with a "
            f"4.7 kΩ pull-up resistor between data and 3.3 V.\n"
            f"Ensure the 1-Wire interface is enabled:\n"
            f"  sudo raspi-config → Interface Options → 1-Wire → Enable\n"
            f"Then reboot."
        ),
        pins=f"GPIO {CFG.GPIO_DS18B20} (1-Wire)",
    ),
    DeviceCheck(
        key="solenoid_relay",
        name="Solenoid Valve (Relay)",
        description="Controls the water inlet solenoid valve.",
        check_fn=_check_solenoid_relay,
        troubleshoot=(
            f"Connect the relay module signal pin to GPIO {CFG.GPIO_RELAY_SOLENOID} (BCM).\n"
            f"Provide 5 V and GND to the relay module from the Pi.\n"
            f"Verify the relay board jumper is set for the correct "
            f"trigger level (active-{'low' if CFG.RELAY_ACTIVE_LOW else 'high'})."
        ),
        pins=f"GPIO {CFG.GPIO_RELAY_SOLENOID}",
    ),
    DeviceCheck(
        key="paddle_relay",
        name="Mixing Paddle (Relay)",
        description="Controls the AC mixing paddle motor.",
        check_fn=_check_paddle_relay,
        troubleshoot=(
            f"Connect the relay module signal pin to GPIO {CFG.GPIO_RELAY_PADDLE} (BCM).\n"
            f"Provide 5 V and GND to the relay module from the Pi.\n"
            f"Verify the relay board jumper is set for the correct "
            f"trigger level (active-{'low' if CFG.RELAY_ACTIVE_LOW else 'high'})."
        ),
        pins=f"GPIO {CFG.GPIO_RELAY_PADDLE}",
    ),
    DeviceCheck(
        key="flow_meter",
        name="Flow Meter (FL-608)",
        description="Counts water pulses to measure volume dispensed.",
        check_fn=_check_flow_meter,
        troubleshoot=(
            f"Connect the flow meter signal (yellow) wire to GPIO {CFG.GPIO_FLOW_METER} (BCM).\n"
            f"Connect red wire to 5 V and black wire to GND.\n"
            f"The internal pull-up resistor is enabled automatically."
        ),
        pins=f"GPIO {CFG.GPIO_FLOW_METER}",
    ),
    DeviceCheck(
        key="ultrasonic",
        name="Ultrasonic Level Sensor (JSN-SR04T)",
        description="Measures tank water level via ultrasonic distance.",
        check_fn=_check_ultrasonic,
        troubleshoot=(
            f"Connect TRIG to GPIO {CFG.GPIO_ULTRA_TRIGGER} and "
            f"ECHO to GPIO {CFG.GPIO_ULTRA_ECHO} (BCM).\n"
            f"Power the sensor with 5 V and GND.\n"
            f"IMPORTANT: Use a voltage divider on the ECHO pin to step\n"
            f"5 V down to 3.3 V (e.g. 1 kΩ + 2 kΩ divider) to protect the Pi.\n"
            f"Mount the sensor at the top of the tank, pointing straight down."
        ),
        pins=f"GPIO {CFG.GPIO_ULTRA_TRIGGER} (trig), GPIO {CFG.GPIO_ULTRA_ECHO} (echo)",
    ),
]


def run_all_checks(hw: "HardwareManager") -> list[CheckResult]:
    """Run detection checks for every registered device."""
    results: list[CheckResult] = []
    for dev in DEVICE_REGISTRY:
        try:
            detected = dev.check_fn(hw)
            results.append(CheckResult(device=dev, detected=detected))
        except Exception as exc:
            log.error("Check failed for %s: %s", dev.key, exc)
            results.append(CheckResult(device=dev, detected=False, detail=str(exc)))
    return results
