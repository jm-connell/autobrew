# AutoBrew — Automated Fertilizer Brewing Controller

Raspberry Pi 5-based controller for a 300–500 gallon stainless steel
fertilizer brewing tank. Manages water filling, timed stirring cycles,
temperature monitoring, and power-loss recovery via a 7″ touchscreen UI.

---

## Hardware Wiring Summary

### GPIO Pin Map (BCM numbering)

| GPIO | Function                       | Notes                                     |
| ---- | ------------------------------ | ----------------------------------------- |
| 4    | DS18B20 temp probe (1-Wire)    | 4.7 kΩ pull-up to 3.3 V                   |
| 17   | Relay → 12 V solenoid valve    | Relay switches +12 V line                 |
| 27   | Relay → AC mixing paddle       | 10 A+ relay channel                       |
| 23   | Ultrasonic trigger (JSN-SR04T) |                                           |
| 24   | Ultrasonic echo (JSN-SR04T)    | Voltage divider: 1 kΩ + 2 kΩ → 3.3 V safe |
| 25   | Flow meter pulse (FL-608)      | Voltage divider: 1 kΩ + 2 kΩ → 3.3 V safe |

### Wiring Details

**DS18B20 Temperature Probe**

- Red → 3.3 V
- Black → GND
- Yellow → GPIO 4
- 4.7 kΩ resistor between 3.3 V and GPIO 4 (pull-up)

**DIGITEN FL-608 Flow Meter (5 V pulse output → 3.3 V GPIO)**

```
Flow meter yellow (signal) ──┬── 1 kΩ ── GPIO 25
                             │
                             └── 2 kΩ ── GND
Flow meter red → 5 V
Flow meter black → GND
```

**JSN-SR04T Ultrasonic Sensor (5 V echo → 3.3 V GPIO)**

- VCC → 5 V, GND → GND, Trigger → GPIO 23
- Echo output through voltage divider:

```
Echo pin ──┬── 1 kΩ ── GPIO 24
           │
           └── 2 kΩ ── GND
```

**US Solid 12 V Solenoid Valve**

- 12 V PSU (+) → relay COM
- Relay NO → solenoid (+)
- Solenoid (−) → 12 V PSU (−)
- Relay signal controlled by GPIO 17

**AC Mixing Paddle**

- Hot line interrupted through relay (GPIO 27 channel)
- Ensure relay is rated ≥ 10 A for motor inrush current

> **Inline sediment filter** should be installed upstream of the solenoid
> to prevent debris from jamming the valve.

---

## Software Setup

### 1. Enable 1-Wire on the Pi

```bash
sudo raspi-config
# → Interface Options → 1-Wire → Enable → Reboot
```

Or add to `/boot/firmware/config.txt`:

```
dtoverlay=w1-gpio,gpiopin=4
```

### 2. Clone / copy files to the Pi

```bash
mkdir -p /home/pi/brewer-controller
# Copy all project files into /home/pi/brewer-controller/
```

### 3. Create a virtual environment and install dependencies

```bash
cd /home/pi/brewer-controller
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Test run

```bash
source venv/bin/activate
python main.py
```

Press **Escape** to exit full-screen mode.

### 5. Install as a systemd service (auto-start on boot)

```bash
sudo cp autobrew.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable autobrew.service
sudo systemctl start autobrew.service
```

Check logs:

```bash
journalctl -u autobrew -f
```

---

## Project Structure

```
brewer-controller/
├── main.py              # Entry point
├── config.py            # All constants, GPIO pins, calibration values
├── hardware.py          # GPIO / sensor abstraction layer
├── controller.py        # Brew-cycle state machine (fill → brew → complete)
├── state_manager.py     # JSON state persistence for power-loss recovery
├── ui.py                # Tkinter touchscreen GUI
├── logger_setup.py      # Centralised logging
├── requirements.txt     # Python dependencies
├── autobrew.service     # systemd unit file
└── README.md            # This file
```

---

## Configuration

Tuneable parameters are split across:

- `calibration.py` — wiring, flow calibration, tank geometry, relay polarity
- `process_defaults.py` — brew defaults, timing, UI refresh and look

`config.py` remains as a backward-compatible facade (`import config as CFG`).

| Parameter                    | Default       | Description                                |
| ---------------------------- | ------------- | ------------------------------------------ |
| `FLOW_PULSES_PER_GALLON`     | 1703          | Flow meter calibration (pulses per gallon) |
| `TANK_CAPACITY_GALLONS`      | 500           | Max working capacity of tank               |
| `TANK_HEIGHT_CM`             | 120           | Sensor-face to tank-bottom distance        |
| `TANK_OVERFILL_PCT`          | 95%           | Level at which fill is vetoed              |
| `LEVEL_SENSOR_FAILSAFE_STOP` | True          | Stop fill if level read fails              |
| `DEFAULT_DILUTION_RATIO`     | 10            | lb water per lb fertilizer                 |
| `STIR_ON_SECONDS`            | 300 (5 min)   | Stirring duration per cycle                |
| `STIR_CYCLE_SECONDS`         | 1800 (30 min) | Total cycle period (stir + rest)           |
| `RELAY_ACTIVE_LOW`           | True          | Set based on your relay module             |

### Flow Meter Calibration

To calibrate, run a known volume of water through the meter and count
pulses. Update `FLOW_PULSES_PER_GALLON` in `config.py`.

### Tank Geometry (Ultrasonic Sensor)

Mount the JSN-SR04T at the top of the tank pointing straight down.
Measure and set `TANK_EMPTY_DISTANCE_CM` and `TANK_FULL_DISTANCE_CM`.
The system uses linear interpolation to estimate fill percentage.

---

## How It Works

1. **Startup** — checks for a saved state file. If a previous cycle was
   interrupted (power loss), prompts the user to resume or start fresh.

2. **New Cycle Setup** — user enters fertilizer weight (lb), dilution
   ratio, and brew duration (1–36 hours). A checkbox allows skipping
   the water-fill phase.

3. **Fill Phase** — opens the solenoid valve and counts flow-meter
   pulses until the calculated target gallons are reached. The
   ultrasonic level sensor acts as a safety veto: if the tank reaches
   95% full, the solenoid closes immediately.

4. **Brew Phase** — the mixing paddle runs for 5 minutes every 30
   minutes. Temperature and elapsed time are displayed continuously.

5. **Completion** — all relays are de-energised and the user is prompted
   to start a new cycle.

6. **State Saving** — every 60 seconds the current state is written to
   `brew_state.json` so the cycle can be resumed after a power loss.

---

## Safety Features

- **Overfill veto** — ultrasonic sensor stops fill if level ≥ 95%
- **Emergency stop button** — immediately de-energises all relays
- **State persistence** — recovers from power loss with user confirmation
- **Sensor error handling** — invalid temperature readings trigger alerts
- **Atomic state writes** — write-to-temp + rename prevents corruption

---

## Notes

- **No heater control** is implemented. Temperature is monitored and
  displayed only. Heater logic (PID, relay toggling) can be added later.
- **No RTC required** — all timing uses `time.monotonic()` for relative
  accuracy. Wall-clock timestamps in the state file are informational.
- The UI runs in Tkinter and is optimised for the 800×480 7″ DSI display.
- On non-Pi platforms the hardware layer runs in mock mode so the UI can
  be developed and tested without GPIO access.
