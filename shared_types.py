"""shared_types.py — Shared types for AutoBrew.

Keeping these in a dedicated module prevents circular imports between
controller/state/ui.

Note: this file intentionally avoids the name `types.py` to prevent
confusion with Python's standard-library module `types`.
"""

from enum import Enum


class Phase(str, Enum):
    IDLE = "idle"
    FILL = "fill"
    BREW = "brew"
    COMPLETE = "complete"
    STOPPED = "stopped"
    ERROR = "error"


STATE_VERSION = 1
