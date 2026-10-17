"""Notizen gesammelt ausgeben: alle Tagesnotizen eines Monats als Text.

Gedacht fuer die anderen im Team - zum Weiterleiten per Mail oder
Messenger (Notizen-Reiter: "Alle kopieren") oder als Textdatei
(Datei > Exportieren > Notizen). Zu jeder Notiz steht, wer an dem Tag
eingeteilt ist; nicht gewaehlte Kandidaten zaehlen wie ueberall nicht.
Urlaub und Wuensche erscheinen bewusst nicht (vertraulich).
"""
from pathlib import Path
from datetime import date

from models import (
    MonthPlan, ShiftType, SHIFT_LABELS, WEEKDAYS_DE, is_effective, month_label,
)

_SHIFT_ORDER = list(ShiftType)


def month_notes(plan: MonthPlan) -> list[tuple[int, str]]:
    """Alle nicht leeren Notizen des Monats als (Tag, Text), chronologisch."""
    return sorted(
        (day, text.strip())
        for day, text in plan.notes.items()
        if (text or "").strip()
    )


def day_label(plan: MonthPlan, day: int) -> str:
    """z. B. "Mo 05.10.2026"."""
    d = date(plan.year, plan.month, day)
    return f"{WEEKDAYS_DE[d.weekday()]} {d:%d.%m.%Y}"


def day_staff(plan: MonthPlan, day: int) -> str:
    """Wer ist an dem Tag eingeteilt? z. B. "VOLL: Benno · RB: Doro"."""
    names = {a.id: a.name for a in plan.assistants}
    entries = sorted(
        (e for e in plan.schedule.get(day, [])
         if is_effective(e) and e.assistant_id in names),
        key=lambda e: _SHIFT_ORDER.index(e.shift_type),
    )
    return " · ".join(
        f"{SHIFT_LABELS[e.shift_type]}: {names[e.assistant_id]}" for e in entries
    )


def notes_text(plan: MonthPlan) -> str:
    title = f"Notizen {month_label(plan.year, plan.month)}"
    lines = [title, "=" * len(title), ""]
    notes = month_notes(plan)
    if not notes:
        lines.append("Keine Notizen in diesem Monat.")
    for day, text in notes:
        staff = day_staff(plan, day)
        lines.append(day_label(plan, day) + (f"  ({staff})" if staff else ""))
        lines.extend(f"  {line}" for line in text.splitlines())
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def export_notes(plan: MonthPlan, folder: str | Path) -> str:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    notes_file = folder / f"notizen_{plan.year}_{plan.month:02d}.txt"
    notes_file.write_text(notes_text(plan), encoding="utf-8")
    return str(notes_file)
