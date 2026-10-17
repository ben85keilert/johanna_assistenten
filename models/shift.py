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

# Kurzbezeichnung je Dienstart - einheitlich in Raster, Warnungen und
# Exporten. Die halben Dienste heissen "Tag" und "Nacht"; die internen
# Namen HALF_MORNING/HALF_AFTERNOON bleiben (Dateiformat unveraendert)
SHIFT_LABELS = {
    ShiftType.FULL: "VOLL",
    ShiftType.HALF_MORNING: "Tag",
    ShiftType.HALF_AFTERNOON: "Nacht",
    ShiftType.ON_CALL: "RB",
}

# Ausfuehrliche Bezeichnung (Farben-Dialog, Legenden, Menues)
SHIFT_NAMES = {
    ShiftType.FULL: "Tagesdienst (VOLL)",
    ShiftType.HALF_MORNING: "Tag (halber Dienst)",
    ShiftType.HALF_AFTERNOON: "Nacht (halber Dienst)",
    ShiftType.ON_CALL: "Rufbereitschaft (RB)",
}


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
