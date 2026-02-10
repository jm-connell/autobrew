"""
controller.py — Brew-cycle state machine for the AutoBrew system.

Phases:  idle → fill → brew → complete  (fill can be skipped).

The controller runs its own background thread so the Tkinter UI stays
responsive.  All hardware access is serialised through the thread.
"""

import datetime
import logging
import threading
import time

import config as CFG
from hardware import HardwareManager
from state_manager import new_state, save_state, clear_state

log = logging.getLogger("autobrew.controller")


class BrewController:
    """
    Manages the brew lifecycle.

    Public attributes (read from any thread — written only by the worker):
        state       dict   current state snapshot (same schema as state_manager)
        alert_msg   str    latest alert / warning for the UI (or "")
        running     bool   True while the worker thread is alive
    """

    def __init__(self, hw: HardwareManager):
        self.hw = hw
        self.state: dict = new_state()
        self.alert_msg: str = ""
        self.running: bool = False

        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

        # Manual fill-end button flag (set from UI thread)
        self._manual_end_fill = threading.Event()

    # ------------------------------------------------------------------
    #  Calculation helpers
    # ------------------------------------------------------------------
    @staticmethod
    def calc_target_gallons(fert_lb: float, dilution: float) -> float:
        """
        gallons = (dilution_ratio × fert_weight) / 8.34

        dilution_ratio = lb water per lb fertilizer
        8.34 = approximate lb per US gallon of water
        """
        if fert_lb <= 0 or dilution <= 0:
            return 0.0
        return round((dilution * fert_lb) / CFG.WATER_DENSITY_LB_PER_GAL, 2)

    # ------------------------------------------------------------------
    #  Start a new cycle
    # ------------------------------------------------------------------
    def start_cycle(
        self,
        fert_lb: float,
        dilution: float,
        duration_hours: float,
        skip_fill: bool,
    ):
        """Kick off a new brew cycle (called from UI thread)."""
        if self.running:
            log.warning("start_cycle called while already running")
            return

        target_gal = self.calc_target_gallons(fert_lb, dilution)

        self.state = new_state()
        self.state["fert_weight_lb"] = fert_lb
        self.state["dilution_ratio"] = dilution
        self.state["target_gallons"] = target_gal
        self.state["brew_duration_sec"] = duration_hours * 3600
        self.state["skip_fill"] = skip_fill
        self.state["brew_start_wallclock"] = datetime.datetime.now().isoformat()
        self.state["phase"] = "brew" if skip_fill else "fill"

        self.hw.flow.reset()
        self.alert_msg = ""
        self._stop_event.clear()
        self._manual_end_fill.clear()

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self.running = True
        log.info(
            "Cycle started: %.1f lb fert, ratio=%.1f, target=%.1f gal, "
            "duration=%.1f h, skip_fill=%s",
            fert_lb, dilution, target_gal, duration_hours, skip_fill,
        )

    # ------------------------------------------------------------------
    #  Resume from saved state
    # ------------------------------------------------------------------
    def resume_cycle(self, saved: dict):
        """Resume a previously interrupted cycle."""
        if self.running:
            return
        self.state = saved
        self.hw.flow.set_gallons(saved.get("added_gallons", 0.0))
        self.alert_msg = ""
        self._stop_event.clear()
        self._manual_end_fill.clear()

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self.running = True
        log.info("Cycle RESUMED from phase '%s'", saved.get("phase"))

    # ------------------------------------------------------------------
    #  Stop / cancel
    # ------------------------------------------------------------------
    def stop(self):
        """Gracefully stop the cycle (called from UI or shutdown)."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self.hw.emergency_stop()
        self.running = False
        log.info("Cycle stopped")

    def manual_end_fill(self):
        """Signal from UI: user pressed 'End Fill Now'."""
        self._manual_end_fill.set()

    # ------------------------------------------------------------------
    #  Background worker
    # ------------------------------------------------------------------
    def _run(self):
        """Main worker loop — runs in its own thread."""
        try:
            phase = self.state["phase"]
            if phase == "fill":
                self._do_fill()
                if self._stop_event.is_set():
                    return
                self.state["phase"] = "brew"

            if self.state["phase"] == "brew":
                self._do_brew()

            if not self._stop_event.is_set():
                self.state["phase"] = "complete"
                self.alert_msg = "Brew cycle complete!"
                save_state(self.state)
                log.info("Brew cycle COMPLETE")
        except Exception as exc:
            log.exception("Unhandled error in controller worker: %s", exc)
            self.alert_msg = f"ERROR: {exc}"
            self.hw.emergency_stop()
        finally:
            self.hw.solenoid.off()
            self.hw.paddle.off()
            self.running = False

    # ------------------------------------------------------------------
    #  Fill phase
    # ------------------------------------------------------------------
    def _do_fill(self):
        target = self.state["target_gallons"]
        log.info("Fill phase started — target %.2f gal", target)
        self.hw.solenoid.on()

        last_save = time.monotonic()

        while not self._stop_event.is_set() and not self._manual_end_fill.is_set():
            gallons = self.hw.flow.total_gallons
            self.state["added_gallons"] = round(gallons, 2)

            # Target reached?
            if gallons >= target:
                log.info("Target gallons reached (%.2f ≥ %.2f)", gallons, target)
                break

            # Water level veto — emergency overfill protection
            if self.hw.level.is_full():
                self.alert_msg = "⚠ Tank full — fill stopped (level veto)"
                log.warning(self.alert_msg)
                break

            # Periodic state save
            now = time.monotonic()
            if now - last_save >= CFG.STATE_SAVE_INTERVAL_SEC:
                self._update_temps()
                save_state(self.state)
                last_save = now

            time.sleep(0.25)

        self.hw.solenoid.off()
        # Final state snapshot
        self.state["added_gallons"] = round(self.hw.flow.total_gallons, 2)
        self._update_temps()
        save_state(self.state)
        log.info("Fill phase ended — %.2f gal added", self.state["added_gallons"])

    # ------------------------------------------------------------------
    #  Brew (stir) phase
    # ------------------------------------------------------------------
    def _do_brew(self):
        duration = self.state["brew_duration_sec"]
        elapsed = self.state.get("brew_elapsed_sec", 0.0)
        stir_elapsed = self.state.get("stir_cycle_elapsed_sec", 0.0)

        log.info(
            "Brew phase started — %.0f s total, %.0f s elapsed so far",
            duration, elapsed,
        )

        last_tick = time.monotonic()
        last_save = last_tick

        while elapsed < duration and not self._stop_event.is_set():
            now = time.monotonic()
            dt = now - last_tick
            last_tick = now

            elapsed += dt
            stir_elapsed += dt
            self.state["brew_elapsed_sec"] = round(elapsed, 1)
            self.state["stir_cycle_elapsed_sec"] = round(stir_elapsed, 1)

            # Stirring logic: ON for first STIR_ON_SECONDS of each cycle
            in_stir_window = stir_elapsed <= CFG.STIR_ON_SECONDS
            if in_stir_window and not self.hw.paddle.is_on:
                self.hw.paddle.on()
            elif not in_stir_window and self.hw.paddle.is_on:
                self.hw.paddle.off()

            # Reset stir cycle counter
            if stir_elapsed >= CFG.STIR_CYCLE_SECONDS:
                stir_elapsed = 0.0
                self.state["stir_cycle_elapsed_sec"] = 0.0

            # Periodic save
            if now - last_save >= CFG.STATE_SAVE_INTERVAL_SEC:
                self._update_temps()
                save_state(self.state)
                last_save = now

            time.sleep(0.5)

        self.hw.paddle.off()
        self.state["brew_elapsed_sec"] = round(elapsed, 1)
        self._update_temps()
        save_state(self.state)
        log.info("Brew phase ended — %.0f s elapsed", elapsed)

    # ------------------------------------------------------------------
    #  Temperature helper
    # ------------------------------------------------------------------
    def _update_temps(self):
        c, f = self.hw.temp.read()
        self.state["last_temp_c"] = c
        self.state["last_temp_f"] = f
