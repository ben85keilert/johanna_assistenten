from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date


@dataclass
class AssistantConstraints:
    assistant_id: str
    unavailable_dates: list[date] = field(default_factory=list)
    vacation_ranges: list[tuple[date, date]] = field(default_factory=list)
    max_consecutive_days: int = 3
    # Helfer mit weiter Anreise kommen immer fuer mehrere Tage am Stueck;
    # der Generator plant sie nur in Bloecken von mindestens dieser Laenge ein
    min_block_days: int = 1
    target_shifts: int | None = None


@dataclass
class Assistant:
    id: str
    name: str
    color: str
    constraints: AssistantConstraints
    active: bool = True
