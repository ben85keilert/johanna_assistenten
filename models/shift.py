from __future__ import annotations
from enum import Enum
from dataclasses import dataclass


class ShiftType(str, Enum):
    FULL = "FULL"
    HALF_MORNING = "HALF_MORNING"
    HALF_AFTERNOON = "HALF_AFTERNOON"
    # Rufbereitschaft: ganztaegig, zaehlt in eigener Zaehlung (nie als Dienst)
    ON_CALL = "ON_CALL"


# Dienstarten des Tagesdienstes; Rufbereitschaft zaehlt separat
DUTY_TYPES = (ShiftType.FULL, ShiftType.HALF_MORNING, ShiftType.HALF_AFTERNOON)


def is_duty(shift_type: ShiftType) -> bool:
    return shift_type in DUTY_TYPES


@dataclass
class ShiftEntry:
    assistant_id: str
    shift_type: ShiftType
    locked: bool = False
    # True = vom Zufallsgenerator vergeben (wird beim Neuwuerfeln ersetzt,
    # solange nicht locked); False = von Hand gesetzt (bleibt immer stehen)
    generated: bool = False
