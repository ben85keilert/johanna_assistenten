from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, timedelta


@dataclass
class AssistantConstraints:
    assistant_id: str
    unavailable_dates: list[date] = field(default_factory=list)
    vacation_ranges: list[tuple[date, date]] = field(default_factory=list)
    # Block-Zeiten: sperren wie Urlaub Dienst UND Rufbereitschaft,
    # sind aber eine eigene Kategorie (kein Urlaub)
    blocked_dates: list[date] = field(default_factory=list)
    blocked_ranges: list[tuple[date, date]] = field(default_factory=list)
    max_consecutive_days: int = 3
    # Helfer mit weiter Anreise kommen immer fuer mehrere Tage am Stueck;
    # der Generator plant sie nur in Bloecken von mindestens dieser Laenge ein
    min_block_days: int = 1
    # Mindestabstand in freien Tagen zwischen zwei Einsatzbloecken derselben
    # Person (Dienst und Rufbereitschaft zusammen gezaehlt); 0 = aus.
    # Harte Regel: der Generator unterschreitet den Abstand nie
    min_gap_days: int = 0
    # Rufbereitschaft als Block direkt an den Dienstblock anhaengen
    # ("before" = davor, "after" = danach, "both" = auf beide Seiten
    # aufgeteilt, "none" = aus) - fuer Helfer mit weiter Anreise, die am
    # Stueck vor Ort sein wollen
    oncall_attach: str = "none"
    # Freiwunsch-Kontingent: None = "Alle" (alle Block-Tage hart wie Urlaub,
    # bisheriges Verhalten). Zahl N = die chronologisch ersten N Block-Tage
    # des Monats haben Vorrang (hart), weitere Nachrang (duerfen im
    # Konfliktfall ueberplant werden; Urlaub bleibt immer zwingend)
    free_wish_quota: int | None = None
    # Soll-Dienste als Spanne; None = "Auto" (gleichmaessig verteilen)
    min_shifts: int | None = None
    max_shifts: int | None = None


@dataclass
class Assistant:
    id: str
    name: str
    color: str
    constraints: AssistantConstraints
    active: bool = True


def _collect_days(singles: list[date], ranges: list[tuple[date, date]]) -> set[date]:
    days = set(singles)
    for start, end in ranges:
        d = start
        while d <= end:
            days.add(d)
            d += timedelta(days=1)
    return days


def _normalize_days(days: set[date]) -> tuple[list[date], list[tuple[date, date]]]:
    """Zerlegt eine Tagesmenge normalisiert: zusammenhaengende Folgen
    (>= 2 Tage) werden Zeitraeume, Einzeltage bleiben Einzeltage.
    Ueberlappende/angrenzende Zeitraeume verschmelzen dadurch."""
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
    return singles, ranges


def absence_days(constraints: AssistantConstraints) -> set[date]:
    """Alle Urlaubstage (Einzeltage + Urlaubszeitraeume) als Tagesmenge."""
    return _collect_days(constraints.unavailable_dates, constraints.vacation_ranges)


def set_absence_days(constraints: AssistantConstraints, days: set[date]) -> None:
    """Schreibt die Urlaubs-Tagesmenge normalisiert zurueck."""
    singles, ranges = _normalize_days(days)
    constraints.unavailable_dates = singles
    constraints.vacation_ranges = ranges


def blocked_days(constraints: AssistantConstraints) -> set[date]:
    """Alle Block-Tage (Einzeltage + Zeitraeume) als Tagesmenge."""
    return _collect_days(constraints.blocked_dates, constraints.blocked_ranges)


def set_blocked_days(constraints: AssistantConstraints, days: set[date]) -> None:
    """Schreibt die Block-Tagesmenge normalisiert zurueck."""
    singles, ranges = _normalize_days(days)
    constraints.blocked_dates = singles
    constraints.blocked_ranges = ranges
