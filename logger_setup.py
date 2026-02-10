"""
logger_setup.py — Centralised logging configuration for AutoBrew.

Call  setup_logging()  once at application start.  All modules use the
standard  logging.getLogger("autobrew.xxx")  pattern.
"""

import logging
import sys

import config as CFG


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """
    Configure root 'autobrew' logger with console + file handlers.

    Returns the root autobrew logger.
    """
    logger = logging.getLogger("autobrew")
    logger.setLevel(level)

    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-8s  [%(name)s]  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(level)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # File handler (create dir if needed)
    try:
        CFG.LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(str(CFG.LOG_FILE), encoding="utf-8")
        fh.setLevel(level)
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except OSError as exc:
        logger.warning("Could not create log file %s: %s", CFG.LOG_FILE, exc)

    logger.info("Logging initialised (level=%s)", logging.getLevelName(level))
    return logger
