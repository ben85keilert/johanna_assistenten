from __future__ import annotations
from dataclasses import dataclass
from models import MonthPlan, ShiftType, DUTY_TYPES, is_duty
from .engine import shift_weight, _day_needs, _needs_oncall, _works_on, ON_CALL_KINDS
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

    # Tage ohne Rufbereitschaft
    missing_oncall = [
        day for day in range(1, days_in_month + 1) if _needs_oncall(plan, day)
    ]
    if missing_oncall:
        warnings.append(
            Warning(
                f"Tage ohne Rufbereitschaft: {', '.join(map(str, missing_oncall))}",
                "warning",
            )
        )

    for assistant in plan.assistants:
        if not assistant.active:
            continue

        assigned = 0.0
        oncall = 0
        for entries in plan.schedule.values():
            for e in entries:
                if e.assistant_id != assistant.id:
                    continue
                if is_duty(e.shift_type):
                    assigned += shift_weight(e.shift_type)
                elif e.shift_type == ShiftType.ON_CALL:
                    oncall += 1

        # Ueber Maximum / unter Minimum
        min_shifts = assistant.constraints.min_shifts
        max_shifts = assistant.constraints.max_shifts
        if max_shifts is not None and assigned > max_shifts:
            warnings.append(
                Warning(f"{assistant.name}: {assigned:g} Dienste (max. {max_shifts})", "warning")
            )
        if min_shifts is not None and 0 < assigned < min_shifts:
            warnings.append(
                Warning(f"{assistant.name}: nur {assigned:g} Dienste (min. {min_shifts})", "info")
            )

        # Rufbereitschaft muss der (gewichteten) Dienstzahl entsprechen;
        # bei halben Diensten (x,5) darf auf- oder abgerundet werden
        if (assigned > 0 or oncall > 0) and abs(oncall - assigned) > 0.5:
            warnings.append(
                Warning(
                    f"{assistant.name}: {oncall} Rufbereitschaften bei {assigned:g} "
                    f"Diensten (muss gleich sein)",
                    "warning",
                )
            )

        # Mindestabstand: freie Tage zwischen zwei Einsatzbloecken
        # (Dienst und Rufbereitschaft zusammen gezaehlt)
        min_gap = assistant.constraints.min_gap_days
        if min_gap > 0:
            runs = []
            day = 1
            while day <= days_in_month:
                if not _works_on(plan, assistant.id, day):
                    day += 1
                    continue
                start = day
                while day <= days_in_month and _works_on(plan, assistant.id, day):
                    day += 1
                runs.append((start, day - 1))
            for (_, end1), (start2, _) in zip(runs, runs[1:]):
                gap = start2 - end1 - 1
                if gap < min_gap:
                    warnings.append(
                        Warning(
                            f"{assistant.name}: nur {gap} freie(r) Tag(e) zwischen "
                            f"den Einsaetzen bis zum {end1}. und ab dem {start2}. "
                            f"(mind. {min_gap})",
                            "warning",
                        )
                    )

        # Folgen pruefen (zu lang / zu kurz fuer Anreise-Helfer) -
        # Dienst und Rufbereitschaft getrennt je Art
        min_block = assistant.constraints.min_block_days
        max_block = assistant.constraints.max_consecutive_days

        def check_runs(kinds, kind_label: str):
            day = 1
            while day <= days_in_month:
                if not _works_on(plan, assistant.id, day, kinds):
                    day += 1
                    continue
                start = day
                while day <= days_in_month and _works_on(plan, assistant.id, day, kinds):
                    day += 1
                length = day - start
                if length > max_block:
                    warnings.append(
                        Warning(
                            f"{assistant.name}: {length} Tage{kind_label} am Stueck "
                            f"ab dem {start}. (max. {max_block})",
                            "warning",
                        )
                    )
                # Am Monatsanfang/-ende kann der Block im Nachbarmonat weitergehen
                elif length < min_block and start > 1 and day - 1 < days_in_month:
                    warnings.append(
                        Warning(
                            f"{assistant.name}: nur {length} Tag(e){kind_label} am Stueck "
                            f"ab dem {start}. (kommt mind. {min_block} Tage)",
                            "info",
                        )
                    )

        check_runs(DUTY_TYPES, "")
        check_runs(ON_CALL_KINDS, " Rufbereitschaft")

    return warnings
