#!/usr/bin/env python3
"""
main.py — Entry point for the AutoBrew fertilizer brewing controller.

Initialises logging, hardware, controller, and Tkinter UI, then hands
off to the GUI main-loop.  Cleans up on exit.

Usage (development):
    python main.py

Usage (production — via systemd):
    See autobrew.service
"""

import signal
import sys
import logging

from logger_setup import setup_logging
from hardware import HardwareManager
from controller import BrewController
from ui import BrewApp


def main():
    # ── Logging ───────────────────────────────────────────────────────
    log = setup_logging(level=logging.INFO)
    log.info("═══ AutoBrew Controller starting ═══")

    # ── Hardware ──────────────────────────────────────────────────────
    hw = HardwareManager()

    # ── Controller ────────────────────────────────────────────────────
    ctrl = BrewController(hw)

    # ── Graceful shutdown on SIGTERM / SIGINT ─────────────────────────
    def _shutdown(signum, frame):
        log.info("Signal %s received — shutting down", signum)
        # Use synchronous stop here (service shutdown can wait briefly).
        ctrl.stop()
        hw.cleanup()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    # ── UI ────────────────────────────────────────────────────────────
    try:
        app = BrewApp(hw, ctrl)
        app.run()  # blocks until window closed
    except Exception as exc:
        log.exception("Fatal UI error: %s", exc)
    finally:
        ctrl.stop()
        hw.cleanup()
        log.info("═══ AutoBrew Controller stopped ═══")


if __name__ == "__main__":
    main()
