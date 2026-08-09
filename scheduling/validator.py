from __future__ import annotations
from dataclasses import dataclass
from models import MonthPlan, ShiftType
from .engine import shift_weight, _day_needs, _works_on
import calendar


@dataclass
class Warning:
    message: str
    severity: str  # "info", "warning", "error"


def validate(plan: MonthPlan) -> list[Warning]:
    warnings = []
    year, month = plan.year, plan.month
    days_in_month = calendar.monthrange(year, month)[1]

    # Unbesetzte und nur halb abgedeckte Tage
    unassigned = []
    half_covered = []
    for day in range(1, days_in_month + 1):
        needed = _day_needs(plan, day)
        if needed is None:
            continue
        if needed == ShiftType.FULL:
            unassigned.append(day)
        else:
            label = "NM" if needed == ShiftType.HALF_AFTERNOON else "VM"
            half_covered.append(f"{day}. ({label} fehlt)")

    if unassigned:
        warnings.append(
            Warning(f"Unbesetzte Tage: {', '.join(map(str, unassigned))}", "warning")
        )
    if half_covered:
        warnings.append(
            Warning(f"Nur halb abgedeckte Tage: {', '.join(half_covered)}", "warning")
        )

    for assistant in plan.assistants:
        if not assistant.active:
            continue

        assigned = sum(
            shift_weight(e.shift_type)
            for entries in plan.schedule.values()
            for e in entries
            if e.assistant_id == assistant.id
        )

        # Ueber/Unter Ziel
        target = assistant.constraints.target_shifts
        if target is not None:
            if assigned > target + 1:
                warnings.append(
                    Warning(f"{assistant.name}: {assigned:g} Dienste (Ziel: {target})", "warning")
                )
            elif assigned < target - 1 and assigned > 0:
                warnings.append(
                    Warning(f"{assistant.name}: nur {assigned:g} Dienste (Ziel: {target})", "info")
                )

        # Dienstbloecke pruefen (zu lang / zu kurz fuer Anreise-Helfer)
        min_block = assistant.constraints.min_block_days
        max_block = assistant.constraints.max_consecutive_days
        day = 1
        while day <= days_in_month:
            if not _works_on(plan, assistant.id, day):
                day += 1
                continue
            start = day
            while day <= days_in_month and _works_on(plan, assistant.id, day):
                day += 1
            length = day - start
            if length > max_block:
                warnings.append(
                    Warning(
                        f"{assistant.name}: {length} Tage am Stueck ab dem {start}. "
                        f"(max. {max_block})",
                        "warning",
                    )
                )
            # Am Monatsanfang/-ende kann der Block im Nachbarmonat weitergehen
            elif length < min_block and start > 1 and day - 1 < days_in_month:
                warnings.append(
                    Warning(
                        f"{assistant.name}: nur {length} Tag(e) am Stueck ab dem {start}. "
                        f"(kommt mind. {min_block} Tage)",
                        "info",
                    )
                )

    return warnings
