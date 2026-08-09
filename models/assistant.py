from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, timedelta


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


def absence_days(constraints: AssistantConstraints) -> set[date]:
    """Alle Abwesenheitstage (Einzeltage + Urlaubszeitraeume) als Tagesmenge."""
    days = set(constraints.unavailable_dates)
    for start, end in constraints.vacation_ranges:
        d = start
        while d <= end:
            days.add(d)
            d += timedelta(days=1)
    return days


def set_absence_days(constraints: AssistantConstraints, days: set[date]) -> None:
    """Schreibt eine Tagesmenge normalisiert zurueck: zusammenhaengende
    Folgen (>= 2 Tage) werden Urlaubszeitraeume, Einzeltage bleiben
    Einzeltage. Ueberlappende/angrenzende Zeitraeume verschmelzen dadurch."""
    ordered = sorted(days)
    singles: list[date] = []
    ranges: list[tuple[date, date]] = []
    i = 0
    while i < len(ordered):
        j = i
        while j + 1 < len(ordered) and ordered[j + 1] == ordered[j] + timedelta(days=1):
            j += 1
        if j == i:
            singles.append(ordered[i])
        else:
            ranges.append((ordered[i], ordered[j]))
        i = j + 1
    constraints.unavailable_dates = singles
    constraints.vacation_ranges = ranges
