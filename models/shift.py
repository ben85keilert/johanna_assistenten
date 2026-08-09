from __future__ import annotations
from enum import Enum
from dataclasses import dataclass


class ShiftType(str, Enum):
    FULL = "FULL"
    HALF_MORNING = "HALF_MORNING"
    HALF_AFTERNOON = "HALF_AFTERNOON"


@dataclass
class ShiftEntry:
    assistant_id: str
    shift_type: ShiftType
    locked: bool = False
    # True = vom Zufallsgenerator vergeben (wird beim Neuwuerfeln ersetzt,
    # solange nicht locked); False = von Hand gesetzt (bleibt immer stehen)
    generated: bool = False
