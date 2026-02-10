"""
hardware.py — Hardware abstraction layer for the AutoBrew system.

Wraps all GPIO, relay, sensor, and flow-meter interactions behind a clean
API so the rest of the application never touches raw GPIO directly.

On non-Pi platforms (development) the module falls back to mock objects
so the UI and controller logic can still be tested.
"""

import time
import threading
import logging

import config as CFG

log = logging.getLogger("autobrew.hardware")

# ──────────────────────────────────────────────────────────────────────
# Try to import real Pi libraries; fall back to mocks for dev/testing
# ──────────────────────────────────────────────────────────────────────
try:
    from gpiozero import OutputDevice, DigitalInputDevice
    ON_PI = True
except (ImportError, RuntimeError):
    ON_PI = False
    log.warning("gpiozero not available — running in MOCK mode")

try:
    from w1thermsensor import W1ThermSensor, SensorNotReadyError, NoSensorFoundError
    HAS_W1 = True
except ImportError:
    HAS_W1 = False
    log.warning("w1thermsensor not available — temperature will be simulated")


# ======================================================================
#  Relay helper
# ======================================================================
class RelayChannel:
    """Controls a single relay channel via GPIO."""

    def __init__(self, gpio_pin: int, name: str = "relay"):
        self.name = name
        self._pin = gpio_pin
        self._device = None
        self._state = False  # False = OFF

        if ON_PI:
            # active_high=True means GPIO HIGH energises the relay.
            # If RELAY_ACTIVE_LOW, invert so .on() still means "relay closed".
            self._device = OutputDevice(
                gpio_pin,
                active_high=not CFG.RELAY_ACTIVE_LOW,
                initial_value=False,
            )
        log.info("Relay '%s' initialised on GPIO %d", name, gpio_pin)

    # -- public ---------------------------------------------------------
    def on(self):
        if self._device:
            self._device.on()
        self._state = True
        log.info("Relay '%s' → ON", self.name)

    def off(self):
        if self._device:
            self._device.off()
        self._state = False
        log.info("Relay '%s' → OFF", self.name)

    @property
    def is_on(self) -> bool:
        return self._state

    def cleanup(self):
        self.off()
        if self._device:
            self._device.close()


# ======================================================================
#  Flow Meter  (pulse-counting via interrupt)
# ======================================================================
class FlowMeter:
    """Counts pulses from the DIGITEN FL-608 Hall-effect flow sensor."""

    def __init__(self, gpio_pin: int, pulses_per_gallon: int):
        self._pulses_per_gallon = pulses_per_gallon
        self._pulse_count = 0
        self._lock = threading.Lock()
        self._device = None

        if ON_PI:
            self._device = DigitalInputDevice(gpio_pin, pull_up=True)
            self._device.when_activated = self._on_pulse
        log.info(
            "FlowMeter initialised on GPIO %d (%d pulses/gal)",
            gpio_pin,
            pulses_per_gallon,
        )

    @property
    def pulses_per_gallon(self) -> int:
        return int(self._pulses_per_gallon)

    def set_pulses_per_gallon(self, pulses_per_gallon: int):
        """Update calibration constant without resetting the counter."""
        if pulses_per_gallon <= 0:
            return
        with self._lock:
            self._pulses_per_gallon = int(pulses_per_gallon)
        log.info("FlowMeter calibration updated: %d pulses/gal", pulses_per_gallon)

    def _on_pulse(self):
        with self._lock:
            self._pulse_count += 1

    # -- public ---------------------------------------------------------
    @property
    def total_gallons(self) -> float:
        with self._lock:
            return self._pulse_count / self._pulses_per_gallon

    @property
    def pulse_count(self) -> int:
        with self._lock:
            return self._pulse_count

    def reset(self):
        with self._lock:
            self._pulse_count = 0
        log.info("FlowMeter counter reset")

    def set_gallons(self, gallons: float):
        """Restore counter to a known value (e.g. after power-loss resume)."""
        with self._lock:
            self._pulse_count = int(gallons * self._pulses_per_gallon)
        log.info("FlowMeter counter restored to %.2f gal", gallons)

    def cleanup(self):
        if self._device:
            self._device.close()


# ======================================================================
#  Ultrasonic Level Sensor  (JSN-SR04T)
# ======================================================================
class UltrasonicLevel:
    """
    Reads distance from a JSN-SR04T ultrasonic sensor and converts to
    a tank fill percentage / estimated gallons.

    The sensor is mounted at the top of the tank looking down.  A shorter
    distance means a higher water level.
    """

    def __init__(
        self,
        trigger_pin: int,
        echo_pin: int,
        tank_empty_cm: float = CFG.TANK_EMPTY_DISTANCE_CM,
        tank_full_cm: float = CFG.TANK_FULL_DISTANCE_CM,
        capacity_gal: float = CFG.TANK_CAPACITY_GALLONS,
    ):
        self._empty_cm = tank_empty_cm
        self._full_cm = tank_full_cm
        self._capacity = capacity_gal
        self._trigger_pin = trigger_pin
        self._echo_pin = echo_pin
        self._trigger = None
        self._echo = None

        if ON_PI:
            self._trigger = OutputDevice(trigger_pin)
            self._echo = DigitalInputDevice(echo_pin)
        log.info(
            "UltrasonicLevel initialised (trigger=%d, echo=%d)", trigger_pin, echo_pin
        )

    def set_geometry(self, empty_cm: float, full_cm: float, capacity_gal: float | None = None):
        """Update tank geometry used for % and gallon estimates."""
        if empty_cm <= 0 or full_cm <= 0 or empty_cm <= full_cm:
            return
        self._empty_cm = float(empty_cm)
        self._full_cm = float(full_cm)
        if capacity_gal is not None and capacity_gal > 0:
            self._capacity = float(capacity_gal)
        log.info(
            "Ultrasonic geometry updated: empty=%.1fcm full=%.1fcm cap=%.1fgal",
            self._empty_cm,
            self._full_cm,
            self._capacity,
        )

    def read_distance_cm(self) -> float | None:
        """Send a pulse and measure round-trip time → distance in cm."""
        if not ON_PI or not self._trigger or not self._echo:
            return None  # mock: caller should handle None gracefully

        try:
            # Send 10 µs trigger pulse
            self._trigger.on()
            time.sleep(0.00001)
            self._trigger.off()

            # Wait for echo to go high (timeout after 100 ms)
            start_wait = time.monotonic()
            while not self._echo.is_active:
                if time.monotonic() - start_wait > 0.1:
                    return None  # no echo received

            pulse_start = time.monotonic()

            while self._echo.is_active:
                if time.monotonic() - pulse_start > 0.1:
                    return None  # echo stuck high

            pulse_end = time.monotonic()

            duration = pulse_end - pulse_start
            distance_cm = (duration * 34300.0) / 2.0
            return distance_cm
        except Exception as exc:
            log.error("Ultrasonic read error: %s", exc)
            return None

    def read_level_pct(self) -> float | None:
        """Return fill level as 0-100 %."""
        dist = self.read_distance_cm()
        if dist is None:
            return None
        # Clamp
        dist = max(self._full_cm, min(self._empty_cm, dist))
        pct = 100.0 * (self._empty_cm - dist) / (self._empty_cm - self._full_cm)
        return round(pct, 1)

    def read_gallons(self) -> float | None:
        """Estimated gallons in tank (linear interpolation)."""
        pct = self.read_level_pct()
        if pct is None:
            return None
        return round(self._capacity * pct / 100.0, 1)

    def is_full(self) -> bool:
        """Return True if level ≥ TANK_OVERFILL_PCT — used as fill veto."""
        pct = self.read_level_pct()
        if pct is None:
            return False  # controller decides fail-safe behavior
        return pct >= CFG.TANK_OVERFILL_PCT

    def cleanup(self):
        if self._trigger:
            self._trigger.close()
        if self._echo:
            self._echo.close()


# ======================================================================
#  DS18B20 Temperature Probe
# ======================================================================
class TemperatureProbe:
    """Reads the DS18B20 1-Wire temperature sensor."""

    def __init__(self):
        self._sensor = None
        if HAS_W1:
            try:
                self._sensor = W1ThermSensor()
                log.info("DS18B20 found: %s", self._sensor.id)
            except NoSensorFoundError:
                log.error("No DS18B20 sensor found on 1-Wire bus")
        self._last_c: float | None = None
        self._last_f: float | None = None

    def read(self) -> tuple[float | None, float | None]:
        """Return (celsius, fahrenheit) or (None, None) on failure."""
        if self._sensor is None:
            return (None, None)
        try:
            c = self._sensor.get_temperature()
            if c < CFG.TEMP_INVALID_THRESHOLD:
                log.warning("DS18B20 returned suspect value: %.1f °C", c)
                return (None, None)
            f = c * 9.0 / 5.0 + 32.0
            self._last_c = round(c, 1)
            self._last_f = round(f, 1)
            return (self._last_c, self._last_f)
        except (SensorNotReadyError, Exception) as exc:
            log.error("DS18B20 read error: %s", exc)
            return (None, None)

    @property
    def last_c(self) -> float | None:
        return self._last_c

    @property
    def last_f(self) -> float | None:
        return self._last_f

    def cleanup(self):
        pass  # nothing to release


# ======================================================================
#  Unified Hardware Manager
# ======================================================================
class HardwareManager:
    """
    Single point of access for all hardware peripherals.

    Instantiate once in main; pass to controller and UI.
    """

    def __init__(self):
        log.info("Initialising hardware …")
        self.solenoid = RelayChannel(CFG.GPIO_RELAY_SOLENOID, "solenoid")
        self.paddle = RelayChannel(CFG.GPIO_RELAY_PADDLE, "paddle")
        self.flow = FlowMeter(CFG.GPIO_FLOW_METER, CFG.FLOW_PULSES_PER_GALLON)
        self.level = UltrasonicLevel(CFG.GPIO_ULTRA_TRIGGER, CFG.GPIO_ULTRA_ECHO)
        self.temp = TemperatureProbe()
        log.info("Hardware initialisation complete")

    def emergency_stop(self):
        """Immediately de-energise all relays."""
        self.solenoid.off()
        self.paddle.off()
        log.critical("EMERGENCY STOP — all relays OFF")

    def cleanup(self):
        """Release all hardware resources."""
        self.solenoid.cleanup()
        self.paddle.cleanup()
        self.flow.cleanup()
        self.level.cleanup()
        self.temp.cleanup()
        log.info("Hardware resources released")
