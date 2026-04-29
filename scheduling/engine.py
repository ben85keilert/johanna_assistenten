from __future__ import annotations
import random
from datetime import date, timedelta
from models import MonthPlan, ShiftEntry, ShiftType
import calendar


def is_unavailable(assistant, day: int, year: int, month: int) -> bool:
    d = date(year, month, day)
    if d in assistant.constraints.unavailable_dates:
        return True
    for start, end in assistant.constraints.vacation_ranges:
        if start <= d <= end:
            return True
    return False


def exceeds_consecutive(plan: MonthPlan, assistant_id: str, day: int) -> bool:
    max_days = next(
        (a.constraints.max_consecutive_days for a in plan.assistants if a.id == assistant_id),
        3
    )

    streak = 0
    for check_day in range(day - 1, max(0, day - 3), -1):
        entries = plan.schedule.get(check_day, [])
        if any(e.assistant_id == assistant_id for e in entries):
            streak += 1
        else:
            break

    return streak >= max_days


def generate(plan: MonthPlan, seed: int | None = None, respect_locked: bool = False) -> MonthPlan:
    if seed is not None:
        rng = random.Random(seed)
    else:
        rng = random.Random()

    year, month = plan.year, plan.month
    days_in_month = calendar.monthrange(year, month)[1]

    # Bestimme freie Tage (nicht gesperrt)
    free_days = []
    for day in range(1, days_in_month + 1):
        if respect_locked:
            entries = plan.schedule.get(day, [])
            if any(e.locked for e in entries):
                continue
        else:
            if day in plan.schedule and plan.schedule[day]:
                if not respect_locked:
                    plan.schedule[day] = []

        free_days.append(day)

    if not respect_locked:
        plan.schedule.clear()
        free_days = list(range(1, days_in_month + 1))

    active_assistants = [a for a in plan.assistants if a.active]
    if not active_assistants:
        return plan

    # Zielanzahl pro Assistent
    target_counts = {}
    num_free_days = len(free_days)
    for assistant in active_assistants:
        if assistant.constraints.target_shifts is not None:
            target_counts[assistant.id] = assistant.constraints.target_shifts
        else:
            target_counts[assistant.id] = num_free_days / len(active_assistants)

    # Shuffle free days
    rng.shuffle(free_days)

    # Zaehl aktuell zugewiesene Dienste
    assigned_counts = {}
    for assistant in active_assistants:
        count = sum(
            1 for entries in plan.schedule.values()
            for e in entries
            if e.assistant_id == assistant.id
        )
        assigned_counts[assistant.id] = count

    # Greedy-Zuweisung
    tolerance = 1.5
    for day in free_days:
        # Verfuegbare Assistenten
        available = []
        for assistant in active_assistants:
            if is_unavailable(assistant, day, year, month):
                continue
            if exceeds_consecutive(plan, assistant.id, day):
                continue
            if assigned_counts[assistant.id] < target_counts[assistant.id] + tolerance:
                available.append(assistant)

        if not available:
            # Toleranz lockern
            available = [
                a for a in active_assistants
                if not is_unavailable(a, day, year, month)
                and not exceeds_consecutive(plan, a.id, day)
            ]

        if not available:
            continue

        # Waehle Assistent mit wenigsten Diensten
        chosen = min(
            available,
            key=lambda a: (assigned_counts[a.id], rng.random())
        )

        if day not in plan.schedule:
            plan.schedule[day] = []
        plan.schedule[day].append(
            ShiftEntry(assistant_id=chosen.id, shift_type=ShiftType.FULL)
        )
        assigned_counts[chosen.id] += 1

    return plan
