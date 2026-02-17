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
| 25   | Flow meter pulse (FL-608)      | GPIO input w/ pull-up (divider if push-pull 5 V) |

### Wiring Details

**DS18B20 Temperature Probe**

- Red → 3.3 V
- Black → GND
- Yellow → GPIO 4
- 4.7 kΩ resistor between 3.3 V and GPIO 4 (pull-up)

**DIGITEN FL-608 Flow Meter (5 V pulse output → 3.3 V GPIO)**

The code enables the Pi's internal pull-up on the flow-meter GPIO input.
Many Hall-effect flow sensors present an **open-collector** output, in which case
this is safe and you can wire the signal directly to the Pi.

If your specific sensor outputs a **push-pull 5 V** digital signal, use a voltage
divider or level shifter to protect the Pi.

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

### 0. Install OS packages

Tkinter is required for the touchscreen UI. On Raspberry Pi OS / Debian this is
usually provided by `python3-tk`.

```bash
sudo apt-get update
sudo apt-get install -y python3-venv python3-tk
```

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

# This path is significant: by default AutoBrew writes logs/state/settings under
# /home/pi/brewer-controller (see calibration.py).
#
# If you want to store logs/state elsewhere, set:
#   AUTOBREW_STATE_DIR=/some/path
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
├── config.py            # Backward-compatible config facade (imports defaults + calibration + settings)
├── calibration.py       # Wiring + calibration constants (defaults)
├── process_defaults.py  # Brew/UI defaults
├── hardware.py          # GPIO / sensor abstraction layer
├── hardware_check.py    # Per-device detection checks for the setup wizard
├── controller.py        # Brew-cycle state machine (fill → brew → complete)
├── state_manager.py     # JSON state persistence for power-loss recovery
├── settings_manager.py  # Persistent per-unit calibration settings (settings.json)
├── shared_types.py      # Shared enums/types (Phase, state version)
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

Per-unit calibration is stored in `/home/pi/brewer-controller/settings.json` and loaded automatically at startup.
On first boot (or if `calibration_complete` is false), the UI forces the first-time setup flow.

The runtime config constants come from `calibration.py` + `process_defaults.py`, then are overridden at import time
by values found in `settings.json` (via `config.apply_runtime_settings()`).

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

In `settings.json`, these are stored under lower-case keys (e.g. `flow_pulses_per_gallon`,
`tank_empty_distance_cm`, `tank_full_distance_cm`, `relay_active_low`, `calibration_complete`).

## Hardware Check (Setup Wizard)

AutoBrew includes an **individual component check** screen that validates each connected sensor/actuator.

- On first run, AutoBrew shows **Hardware Check** first, then **Calibration / Setup**.
- Tap any device row to expand/collapse wiring and troubleshooting guidance.
- **Recheck All** reruns every device check.
- **Continue** proceeds to calibration (it does not currently block if a device is missing).
- On non-Pi platforms, some checks may report missing hardware (notably the DS18B20) unless the relevant libraries
   and buses are available; this does not prevent UI development.

What gets checked is defined in `hardware_check.py` as a registry (`DEVICE_REGISTRY`). If you add/remove hardware,
update that list and the UI adapts automatically.

## Calibration (Recommended)

Use the built-in **Calibration / Setup** wizard (available on the setup screen and monitor screen).
It writes per-unit values to `/home/pi/brewer-controller/settings.json` and applies them immediately.

### Flow meter (pulses/gal)

- Put the solenoid discharge into a measured container (or to drain if you can measure volume another way).
- In the wizard, tap **Run Water** to open the solenoid and count pulses.
- Tap **Stop Water**, enter the **actual gallons** dispensed, then **Save Calibration**.

Practical tip: using 10–20 gallons usually gives a more stable calibration than 1–2 gallons.

### Ultrasonic tank geometry (EMPTY/FULL distances)

The ultrasonic sensor measures the distance from the sensor face to the **liquid surface**.
The system uses two distances:

- **Empty distance (cm)** — distance when the tank is considered 0%
- **Full distance (cm)** — distance at your desired “full” working level

You do **not** have to actually fill the tank to calibrate these.

Accepted calibration methods:

- **Best / most repeatable:** hold a **flat target** (clipboard/board/cardboard) under the sensor at the
  desired distance and tap **Use current as EMPTY/FULL**.
- **Works in a pinch:** hold your **hand** under the sensor and tap **Use current as EMPTY/FULL**.
  (Hands are not perfectly flat, so readings can vary more.)
- **Most accurate:** measure the distances with a tape measure and type them into the fields.

If you _do_ prefer filling the tank: fill to your intended working “full” level, then tap **Use current as FULL**.

---

## How It Works

1. **Startup** — loads per-unit settings from `settings.json`. If calibration
   is not complete, forces the first-time setup flow:
   **Hardware Check → Calibration / Setup**.

2. **Resume detection** — after calibration is complete, checks for a saved
   `brew_state.json`. If a previous cycle was interrupted (power loss), prompts
   the user to resume or start fresh.

3. **New Cycle Setup** — user enters fertilizer weight (lb), dilution
   ratio, and brew duration (1–36 hours). A checkbox allows skipping
   the water-fill phase.

4. **Fill Phase** — opens the solenoid valve and counts flow-meter
   pulses until the calculated target gallons are reached. The
   ultrasonic level sensor acts as a safety veto: if the tank reaches
   95% full, the solenoid closes immediately.

5. **Brew Phase** — the mixing paddle runs for 5 minutes every 30
   minutes. Temperature and elapsed time are displayed continuously.

6. **Completion** — all relays are de-energised and the user is prompted
   to start a new cycle.

7. **State Saving** — every 60 seconds the current state is written to
   `brew_state.json` so the cycle can be resumed after a power loss.

---

## Safety Features

- **Overfill veto** — ultrasonic sensor stops fill if level ≥ 95%
- **Emergency stop button** — immediately de-energises all relays
- **State persistence** — recovers from power loss with user confirmation
- **Temperature sanity check** — ignores suspect DS18B20 readings
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
- Persistent files (defaults):
   - `/home/pi/brewer-controller/brew_state.json` — resume state
   - `/home/pi/brewer-controller/settings.json` — per-unit calibration
   - `/home/pi/brewer-controller/autobrew.log` — file logs (in addition to journalctl when run as a service)
