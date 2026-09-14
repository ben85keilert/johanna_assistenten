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
    # Kandidaten-Mechanik (nur FULL und ON_CALL): candidate=True markiert
    # einen von mehreren manuellen Vorschlaegen fuer den Tag - er zaehlt
    # erst als Abdeckung/Soll, wenn chosen=True (Wahl durch Wuerfeln oder
    # von Hand; Neuwuerfeln setzt eine nicht fixierte Wahl zurueck)
    candidate: bool = False
    chosen: bool = False


def is_effective(entry: ShiftEntry) -> bool:
    """Zaehlt dieser Eintrag als echte Belegung? Nicht gewaehlte
    Kandidaten sind nur Vorschlaege - keine Abdeckung, kein Soll."""
    return not entry.candidate or entry.chosen
