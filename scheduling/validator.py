from __future__ import annotations
from dataclasses import dataclass
from models import MonthPlan, ShiftType, DUTY_TYPES, is_duty, is_effective
from .engine import (
    shift_weight, _day_needs, _needs_oncall, _works_on, ON_CALL_KINDS,
    is_blocked, is_on_vacation,
)
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

    # Kandidaten-Tage ohne getroffene Wahl (Tag zaehlt oben schon als offen;
    # dieser Hinweis erklaert, warum: es liegt eine Auswahl bereit)
    label = {ShiftType.FULL: "Dienst", ShiftType.ON_CALL: "Rufbereitschaft"}
    for day in range(1, days_in_month + 1):
        entries = plan.schedule.get(day, [])
        for shift_type, kind_label in label.items():
            candidates = [
                e for e in entries
                if e.candidate and e.shift_type == shift_type
            ]
            if candidates and not any(e.chosen for e in candidates):
                warnings.append(
                    Warning(
                        f"Tag {day}: mehrere Kandidaten fuer {kind_label}, "
                        "keiner gewaehlt",
                        "info",
                    )
                )

    # Doppelbelegung: eine Person mit mehr als einem wirksamen Eintrag am Tag
    # (z. B. fest gewaehlter Kandidat kollidiert mit anderem Eintrag)
    for day in range(1, days_in_month + 1):
        seen: dict[str, int] = {}
        for e in plan.schedule.get(day, []):
            if is_effective(e):
                seen[e.assistant_id] = seen.get(e.assistant_id, 0) + 1
        for assistant in plan.assistants:
            if seen.get(assistant.id, 0) > 1:
                warnings.append(
                    Warning(
                        f"{assistant.name}: mehrere Eintraege am {day}. "
                        "(Dienst und Rufbereitschaft schliessen sich aus)",
                        "warning",
                    )
                )

    for assistant in plan.assistants:
        if not assistant.active:
            continue

        assigned = 0.0
        oncall = 0
        overridden_wishes = []
        for day, entries in plan.schedule.items():
            for e in entries:
                if e.assistant_id != assistant.id or not is_effective(e):
                    continue
                if is_duty(e.shift_type):
                    assigned += shift_weight(e.shift_type)
                elif e.shift_type == ShiftType.ON_CALL:
                    oncall += 1
                # Wirksamer Eintrag auf eigenem Block-Tag = ueberplanter
                # Freiwunsch (Urlaub wird nie ueberplant und hat Vorrang)
                if (is_blocked(assistant, day, year, month)
                        and not is_on_vacation(assistant, day, year, month)):
                    overridden_wishes.append(day)
        if overridden_wishes:
            days_text = ", ".join(f"{d}." for d in sorted(overridden_wishes))
            warnings.append(
                Warning(
                    f"Freiwunsch ueberplant: {assistant.name} am {days_text}",
                    "warning",
                )
            )

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

        def presence_length(start: int, end: int) -> int:
            """Laenge der zusammenhaengenden Anwesenheit um start..end herum -
            Dienst und Rufbereitschaft zusammen. Wer die Rufbereitschaft an
            den Dienstblock anhaengt (auch beidseitig), ist am Stueck vor Ort;
            die kuerzeren Teilstuecke sind dann kein zu kurzer Einsatz."""
            first, last = start, end
            while first > 1 and _works_on(plan, assistant.id, first - 1):
                first -= 1
            while last < days_in_month and _works_on(plan, assistant.id, last + 1):
                last += 1
            return last - first + 1

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
                elif (length < min_block and start > 1 and day - 1 < days_in_month
                      and presence_length(start, day - 1) < min_block):
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
