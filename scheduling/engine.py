"""Zufallsgenerator fuer den Monatsplan.

Zyklus (siehe BESCHREIBUNG.md):
- Manuell gesetzte Eintraege (generated=False) und fixierte (locked=True)
  bleiben immer stehen und zaehlen fuer die Zielverteilung mit.
- Nicht fixierte Zufalls-Eintraege werden bei jedem Aufruf entfernt und
  neu gewuerfelt ("was nicht gefaellt, wird neu vergeben").

Abdeckung: Ein Tag ist voll abgedeckt durch 1x VOLL oder VM + NM.
Halbe Dienste zaehlen 0,5 fuer die Zielverteilung.
Helfer mit min_block_days > 1 werden nur in zusammenhaengenden Bloecken
eingeplant (weite Anreise).
"""
from __future__ import annotations
import random
import calendar
from datetime import date
from models import MonthPlan, ShiftEntry, ShiftType


def is_unavailable(assistant, day: int, year: int, month: int) -> bool:
    d = date(year, month, day)
    if d in assistant.constraints.unavailable_dates:
        return True
    for start, end in assistant.constraints.vacation_ranges:
        if start <= d <= end:
            return True
    return False


def shift_weight(shift_type: ShiftType) -> float:
    return 1.0 if shift_type == ShiftType.FULL else 0.5


def _works_on(plan: MonthPlan, assistant_id: str, day: int) -> bool:
    return any(e.assistant_id == assistant_id for e in plan.schedule.get(day, []))


def _run_length_if_assigned(plan: MonthPlan, assistant_id: str, first_day: int, last_day: int) -> int:
    """Laenge der zusammenhaengenden Dienstfolge, wenn first_day..last_day
    zusaetzlich zugewiesen wuerden (bestehende Nachbartage zaehlen mit)."""
    length = last_day - first_day + 1
    day = first_day - 1
    while day >= 1 and _works_on(plan, assistant_id, day):
        length += 1
        day -= 1
    day = last_day + 1
    while _works_on(plan, assistant_id, day):
        length += 1
        day += 1
    return length


def exceeds_consecutive(plan: MonthPlan, assistant_id: str, day: int) -> bool:
    """True, wenn ein Dienst an diesem Tag die max. Folgetage ueberschreiten wuerde."""
    max_days = next(
        (a.constraints.max_consecutive_days for a in plan.assistants if a.id == assistant_id),
        3,
    )
    return _run_length_if_assigned(plan, assistant_id, day, day) > max_days


def _day_needs(plan: MonthPlan, day: int) -> ShiftType | None:
    """Welcher Dienst fehlt an diesem Tag noch? None = Tag ist abgedeckt."""
    entries = plan.schedule.get(day, [])
    if any(e.shift_type == ShiftType.FULL for e in entries):
        return None
    has_vm = any(e.shift_type == ShiftType.HALF_MORNING for e in entries)
    has_nm = any(e.shift_type == ShiftType.HALF_AFTERNOON for e in entries)
    if has_vm and has_nm:
        return None
    if has_vm:
        return ShiftType.HALF_AFTERNOON
    if has_nm:
        return ShiftType.HALF_MORNING
    return ShiftType.FULL


def _add_entry(plan: MonthPlan, day: int, assistant_id: str, shift_type: ShiftType) -> None:
    plan.schedule.setdefault(day, []).append(
        ShiftEntry(assistant_id=assistant_id, shift_type=shift_type, generated=True)
    )


def generate(plan: MonthPlan, seed: int | None = None) -> MonthPlan:
    rng = random.Random(seed) if seed is not None else random.Random()
    year, month = plan.year, plan.month
    days_in_month = calendar.monthrange(year, month)[1]

    # 1. Nicht fixierte Zufalls-Eintraege entfernen (Neuwuerfeln)
    for day in list(plan.schedule.keys()):
        plan.schedule[day] = [
            e for e in plan.schedule[day] if not e.generated or e.locked
        ]
        if not plan.schedule[day]:
            del plan.schedule[day]

    active = [a for a in plan.assistants if a.active]
    if not active:
        return plan

    # 2. Zielzahlen und bereits vergebene Dienste (VOLL=1, VM/NM=0,5)
    assigned = {a.id: 0.0 for a in active}
    for entries in plan.schedule.values():
        for e in entries:
            if e.assistant_id in assigned:
                assigned[e.assistant_id] += shift_weight(e.shift_type)

    targets = {}
    for a in active:
        if a.constraints.target_shifts is not None:
            targets[a.id] = float(a.constraints.target_shifts)
        else:
            targets[a.id] = days_in_month / len(active)

    tolerance = 1.5

    def candidates(day: int, needed_weight: float, pool) -> list:
        result = []
        for a in pool:
            if _works_on(plan, a.id, day):
                continue
            if is_unavailable(a, day, year, month):
                continue
            if exceeds_consecutive(plan, a.id, day):
                continue
            if assigned[a.id] + needed_weight <= targets[a.id] + tolerance:
                result.append(a)
        return result

    def pick(pool: list):
        return min(pool, key=lambda a: (assigned[a.id], rng.random()))

    block_assistants = [a for a in active if a.constraints.min_block_days > 1]
    single_assistants = [a for a in active if a.constraints.min_block_days <= 1]

    # 3. Blockvergabe: Helfer mit weiter Anreise bekommen zusammenhaengende
    #    VOLL-Bloecke von min_block_days Laenge auf noch komplett freien Tagen
    rng.shuffle(block_assistants)
    for a in block_assistants:
        block_len = a.constraints.min_block_days
        while assigned[a.id] + block_len <= targets[a.id] + tolerance:
            starts = []
            for start in range(1, days_in_month - block_len + 2):
                days = range(start, start + block_len)
                if not all(_day_needs(plan, d) == ShiftType.FULL for d in days):
                    continue
                if any(is_unavailable(a, d, year, month) for d in days):
                    continue
                run = _run_length_if_assigned(plan, a.id, start, start + block_len - 1)
                if run > a.constraints.max_consecutive_days:
                    continue
                starts.append(start)
            if not starts:
                break
            start = rng.choice(starts)
            for d in range(start, start + block_len):
                _add_entry(plan, d, a.id, ShiftType.FULL)
            assigned[a.id] += block_len

    # 4. Restliche Tage einzeln fuellen (VOLL fuer leere Tage,
    #    fehlende Haelfte fuer halb abgedeckte Tage)
    open_days = [d for d in range(1, days_in_month + 1) if _day_needs(plan, d) is not None]
    rng.shuffle(open_days)
    for day in open_days:
        needed = _day_needs(plan, day)
        if needed is None:
            continue
        weight = shift_weight(needed)

        # Blockfahrer nur als Notloesung fuer einzelne Resttage
        available = candidates(day, weight, single_assistants)
        if not available:
            available = candidates(day, weight, block_assistants)
        if not available:
            # Toleranz lockern: Zielzahl-Grenze ignorieren
            available = [
                a for a in active
                if not _works_on(plan, a.id, day)
                and not is_unavailable(a, day, year, month)
                and not exceeds_consecutive(plan, a.id, day)
            ]
        if not available:
            continue

        chosen = pick(available)
        _add_entry(plan, day, chosen.id, needed)
        assigned[chosen.id] += weight

    return plan
