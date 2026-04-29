from __future__ import annotations
from dataclasses import dataclass
from models import MonthPlan
import calendar


@dataclass
class Warning:
    message: str
    severity: str  # "info", "warning", "error"


def validate(plan: MonthPlan) -> list[Warning]:
    warnings = []
    year, month = plan.year, plan.month
    days_in_month = calendar.monthrange(year, month)[1]

    # Unbesetzte Tage
    unassigned = []
    for day in range(1, days_in_month + 1):
        entries = plan.schedule.get(day, [])
        if not entries:
            unassigned.append(day)

    if unassigned:
        warnings.append(
            Warning(
                f"Unbesetzte Tage: {', '.join(map(str, unassigned))}",
                "warning"
            )
        )

    # Ueber/Unter Ziel
    for assistant in plan.assistants:
        if not assistant.active:
            continue

        assigned = sum(
            1 for entries in plan.schedule.values()
            for e in entries
            if e.assistant_id == assistant.id
        )

        target = assistant.constraints.target_shifts
        if target is not None:
            if assigned > target + 1:
                warnings.append(
                    Warning(
                        f"{assistant.name}: {assigned} Dienste (Ziel: {target})",
                        "warning"
                    )
                )
            elif assigned < target - 1 and assigned > 0:
                warnings.append(
                    Warning(
                        f"{assistant.name}: nur {assigned} Dienste (Ziel: {target})",
                        "info"
                    )
                )

    return warnings
