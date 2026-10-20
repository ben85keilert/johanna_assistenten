"""Rueckmeldung in die Helfer-Constraints eintragen.

Ersetzt fuer den Helfer alle Urlaubs-, Wunsch- und Dienstwunsch-Tage des
gemeldeten Monats durch die gemeldeten (andere Monate und andere Helfer
bleiben unberuehrt). Die Abwesenheiten liegen monatsuebergreifend in
team.json - deshalb braucht das Eintragen fuer einen anderen Monat keinen
geladenen Monatsplan.
"""
from __future__ import annotations

from datetime import date, datetime

from models import Assistant, DAY_KINDS
from .parser import Feedback


def last_import(assistant: Assistant, year: int, month: int) -> dict[str, str] | None:
    """{"stand": ..., "eingelesen": ...} der zuletzt eingelesenen Rueckmeldung
    dieses Helfers fuer den Monat, sonst None."""
    return assistant.constraints.feedback_log.get(f"{year}-{month:02d}")


def is_older_than_last(assistant: Assistant, fb: Feedback) -> bool:
    """True, wenn die Rueckmeldung einen aelteren Stand traegt als die zuletzt
    eingelesene (nur vergleichbar, wenn beide einen Zeitstempel haben)."""
    last = last_import(assistant, fb.year, fb.month)
    if not last or not last.get("stand") or not fb.stamp:
        return False
    return fb.stamp < last["stand"]


def existing_counts(assistant: Assistant, year: int, month: int) -> dict[str, int]:
    """Wie viele Tage je Art der Helfer in diesem Monat schon eingetragen hat
    (das, was eine Rueckmeldung ersetzen wuerde)."""
    counts = {}
    for kind, (get_days, _set) in DAY_KINDS.items():
        counts[kind] = sum(
            1 for d in get_days(assistant.constraints)
            if d.year == year and d.month == month
        )
    return counts


def apply_feedback(assistant: Assistant, fb: Feedback) -> None:
    for kind, (get_days, set_days) in DAY_KINDS.items():
        current = get_days(assistant.constraints)
        kept = {d for d in current if (d.year, d.month) != (fb.year, fb.month)}
        new = {date(fb.year, fb.month, d) for d in fb.days.get(kind, ())}
        set_days(assistant.constraints, kept | new)
    # Stand (aus dem Formular) und Importzeit merken - Grundlage der
    # Rueckfrage, wenn spaeter eine aeltere Rueckmeldung kommt
    assistant.constraints.feedback_log[fb.month_key()] = {
        "stand": fb.stamp,
        "eingelesen": datetime.now().isoformat(timespec="seconds"),
    }
