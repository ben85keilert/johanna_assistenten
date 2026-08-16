"""Zufallsgenerator fuer den Monatsplan.

Zyklus (siehe BESCHREIBUNG.md):
- Manuell gesetzte Eintraege (generated=False) und fixierte (locked=True)
  bleiben immer stehen und zaehlen fuer die Zielverteilung mit.
- Nicht fixierte Zufalls-Eintraege werden bei jedem Aufruf entfernt und
  neu gewuerfelt ("was nicht gefaellt, wird neu vergeben").

Abdeckung: Ein Tag braucht einen Tagesdienst (1x VOLL oder VM + NM) und
zusaetzlich eine Rufbereitschaft (RB, ganztaegig) durch eine andere Person.
Halbe Dienste zaehlen 0,5 fuer die Zielverteilung. Pro Person und Tag gibt
es entweder Dienst oder Rufbereitschaft, nie beides.
Jeder Helfer bekommt im Monat genauso viele Rufbereitschaften wie
(gewichtete) Dienste - Ziel ist Gleichstand, nicht nur Annaeherung.
Folgen (Max. Folge, Min. Block) gelten fuer Dienst und RB gleichermassen,
werden aber je Art getrennt gezaehlt.
Helfer mit min_block_days > 1 werden nur in zusammenhaengenden Bloecken
eingeplant (weite Anreise). Mit oncall_attach ("before"/"after") haengt der
Generator die Rufbereitschaft als Block direkt vor bzw. nach den Dienstblock,
damit die Person am Stueck vor Ort ist.
min_gap_days ist der Mindestabstand in freien Tagen zwischen zwei
Einsatzbloecken derselben Person (Dienst und RB zusammen gezaehlt) - eine
harte Regel, die der Generator nie unterschreitet.
"""
from __future__ import annotations
import random
import calendar
from datetime import date
from models import MonthPlan, ShiftEntry, ShiftType, DUTY_TYPES, is_duty

ON_CALL_KINDS = (ShiftType.ON_CALL,)


def is_on_vacation(assistant, day: int, year: int, month: int) -> bool:
    d = date(year, month, day)
    if d in assistant.constraints.unavailable_dates:
        return True
    for start, end in assistant.constraints.vacation_ranges:
        if start <= d <= end:
            return True
    return False


def is_blocked(assistant, day: int, year: int, month: int) -> bool:
    d = date(year, month, day)
    if d in assistant.constraints.blocked_dates:
        return True
    for start, end in assistant.constraints.blocked_ranges:
        if start <= d <= end:
            return True
    return False


def is_unavailable(assistant, day: int, year: int, month: int) -> bool:
    """Urlaub und Block sperren beide Dienst UND Rufbereitschaft."""
    return is_on_vacation(assistant, day, year, month) or is_blocked(
        assistant, day, year, month
    )


def shift_weight(shift_type: ShiftType) -> float:
    return 0.5 if shift_type in (ShiftType.HALF_MORNING, ShiftType.HALF_AFTERNOON) else 1.0


def _works_on(plan: MonthPlan, assistant_id: str, day: int,
              kinds: tuple[ShiftType, ...] | None = None) -> bool:
    """kinds=None: irgendein Eintrag (Tages-Exklusivitaet),
    sonst nur Eintraege der angegebenen Dienstarten."""
    return any(
        e.assistant_id == assistant_id and (kinds is None or e.shift_type in kinds)
        for e in plan.schedule.get(day, [])
    )


def _run_length_if_assigned(plan: MonthPlan, assistant_id: str,
                            first_day: int, last_day: int,
                            kinds: tuple[ShiftType, ...] = DUTY_TYPES) -> int:
    """Laenge der zusammenhaengenden Folge dieser Dienstart, wenn
    first_day..last_day zusaetzlich zugewiesen wuerden (bestehende
    Nachbartage derselben Art zaehlen mit)."""
    length = last_day - first_day + 1
    day = first_day - 1
    while day >= 1 and _works_on(plan, assistant_id, day, kinds):
        length += 1
        day -= 1
    day = last_day + 1
    while _works_on(plan, assistant_id, day, kinds):
        length += 1
        day += 1
    return length


def exceeds_consecutive(plan: MonthPlan, assistant_id: str, day: int,
                        kinds: tuple[ShiftType, ...] = DUTY_TYPES) -> bool:
    """True, wenn ein Eintrag dieser Art an diesem Tag die max. Folgetage
    ueberschreiten wuerde (je Art getrennt gezaehlt)."""
    max_days = next(
        (a.constraints.max_consecutive_days for a in plan.assistants if a.id == assistant_id),
        3,
    )
    return _run_length_if_assigned(plan, assistant_id, day, day, kinds) > max_days


def _violates_min_gap(plan: MonthPlan, assistant, first_day: int, last_day: int,
                      days_in_month: int) -> bool:
    """True, wenn ein Einsatz an first_day..last_day den Mindestabstand
    dieser Person unterschreiten wuerde. Der Abstand zaehlt freie Tage
    zwischen zwei getrennten Einsatzbloecken (alle Dienstarten zusammen);
    direkt angrenzende Tage verlaengern den Block und sind erlaubt."""
    min_gap = assistant.constraints.min_gap_days
    if min_gap <= 0:
        return False
    # Kombinierten Einsatzblock bestimmen: angrenzende belegte Tage zaehlen mit
    left = first_day
    while left > 1 and _works_on(plan, assistant.id, left - 1):
        left -= 1
    right = last_day
    while right < days_in_month and _works_on(plan, assistant.id, right + 1):
        right += 1
    # Innerhalb des Mindestabstands vor/nach dem Block darf kein weiterer
    # Einsatz liegen (left-1 bzw. right+1 sind nach dem Erweitern frei)
    for day in range(max(1, left - min_gap), left - 1):
        if _works_on(plan, assistant.id, day):
            return True
    for day in range(right + 2, min(days_in_month, right + min_gap) + 1):
        if _works_on(plan, assistant.id, day):
            return True
    return False


def _day_needs(plan: MonthPlan, day: int) -> ShiftType | None:
    """Welcher Tagesdienst fehlt an diesem Tag noch? None = Tag ist abgedeckt.
    Rufbereitschafts-Eintraege zaehlen hier nicht als Abdeckung."""
    entries = [e for e in plan.schedule.get(day, []) if is_duty(e.shift_type)]
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


def _needs_oncall(plan: MonthPlan, day: int) -> bool:
    """True, wenn an diesem Tag noch keine Rufbereitschaft vergeben ist."""
    return not any(
        e.shift_type == ShiftType.ON_CALL for e in plan.schedule.get(day, [])
    )


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

    # 2. Zielzahlen und bereits vergebene Dienste (VOLL=1, VM/NM=0,5);
    #    Rufbereitschaften zaehlen separat
    assigned = {a.id: 0.0 for a in active}
    oncall_assigned = {a.id: 0 for a in active}
    for entries in plan.schedule.values():
        for e in entries:
            if e.assistant_id not in assigned:
                continue
            if is_duty(e.shift_type):
                assigned[e.assistant_id] += shift_weight(e.shift_type)
            elif e.shift_type == ShiftType.ON_CALL:
                oncall_assigned[e.assistant_id] += 1

    tolerance = 1.5
    fair_share = days_in_month / len(active)

    def duty_cap(a) -> float:
        # Explizites Maximum ist eine harte Grenze (ohne Toleranz);
        # "Auto" verteilt gleichmaessig mit Spielraum
        if a.constraints.max_shifts is not None:
            return float(a.constraints.max_shifts)
        return fair_share + tolerance

    def below_min(a) -> bool:
        minimum = a.constraints.min_shifts
        return minimum is not None and assigned[a.id] < minimum

    def candidates(day: int, needed_weight: float, pool) -> list:
        result = []
        for a in pool:
            if _works_on(plan, a.id, day):
                continue
            if is_unavailable(a, day, year, month):
                continue
            if exceeds_consecutive(plan, a.id, day):
                continue
            if _violates_min_gap(plan, a, day, day, days_in_month):
                continue
            if assigned[a.id] + needed_weight <= duty_cap(a):
                result.append(a)
        return result

    def pick(pool: list):
        # Helfer unter ihrem Minimum zuerst, dann die mit den wenigsten Diensten
        return min(pool, key=lambda a: (0 if below_min(a) else 1, assigned[a.id], rng.random()))

    block_assistants = [a for a in active if a.constraints.min_block_days > 1]
    single_assistants = [a for a in active if a.constraints.min_block_days <= 1]

    # 3. Blockvergabe: Helfer mit weiter Anreise bekommen zusammenhaengende
    #    VOLL-Bloecke von min_block_days Laenge auf noch komplett freien
    #    Tagen. Mit oncall_attach wird der gleich lange RB-Block direkt
    #    davor bzw. danach mit vergeben (Anwesenheit am Stueck)
    rng.shuffle(block_assistants)
    for a in block_assistants:
        block_len = a.constraints.min_block_days
        attach = a.constraints.oncall_attach
        while assigned[a.id] + block_len <= duty_cap(a):
            starts = []
            for start in range(1, days_in_month - block_len + 2):
                days = range(start, start + block_len)
                if not all(_day_needs(plan, d) == ShiftType.FULL for d in days):
                    continue
                # Auch keine eigene Rufbereitschaft an diesen Tagen
                if any(_works_on(plan, a.id, d) for d in days):
                    continue
                if any(is_unavailable(a, d, year, month) for d in days):
                    continue
                run = _run_length_if_assigned(plan, a.id, start, start + block_len - 1)
                if run > a.constraints.max_consecutive_days:
                    continue
                span_first, span_last = start, start + block_len - 1
                if attach in ("before", "after"):
                    rb_start = start - block_len if attach == "before" else start + block_len
                    rb_days = range(rb_start, rb_start + block_len)
                    if rb_days[0] < 1 or rb_days[-1] > days_in_month:
                        continue
                    if not all(_needs_oncall(plan, d) for d in rb_days):
                        continue
                    if any(_works_on(plan, a.id, d) for d in rb_days):
                        continue
                    if any(is_unavailable(a, d, year, month) for d in rb_days):
                        continue
                    rb_run = _run_length_if_assigned(
                        plan, a.id, rb_days[0], rb_days[-1], ON_CALL_KINDS
                    )
                    if rb_run > a.constraints.max_consecutive_days:
                        continue
                    span_first = min(span_first, rb_days[0])
                    span_last = max(span_last, rb_days[-1])
                if _violates_min_gap(plan, a, span_first, span_last, days_in_month):
                    continue
                starts.append(start)
            if not starts:
                break
            start = rng.choice(starts)
            for d in range(start, start + block_len):
                _add_entry(plan, d, a.id, ShiftType.FULL)
            assigned[a.id] += block_len
            if attach in ("before", "after"):
                rb_start = start - block_len if attach == "before" else start + block_len
                for d in range(rb_start, rb_start + block_len):
                    _add_entry(plan, d, a.id, ShiftType.ON_CALL)
                oncall_assigned[a.id] += block_len

    def try_attach_oncall(a, day: int) -> None:
        """Haengt fuer Helfer mit oncall_attach die Rufbereitschaft direkt
        an einen einzeln vergebenen Diensttag an (best effort)."""
        attach = a.constraints.oncall_attach
        if attach not in ("before", "after"):
            return
        rb_day = day - 1 if attach == "before" else day + 1
        if not 1 <= rb_day <= days_in_month:
            return
        if oncall_assigned[a.id] + 1 > assigned[a.id] + 0.5:
            return
        if not _needs_oncall(plan, rb_day):
            return
        if _works_on(plan, a.id, rb_day):
            return
        if is_unavailable(a, rb_day, year, month):
            return
        if exceeds_consecutive(plan, a.id, rb_day, ON_CALL_KINDS):
            return
        if _violates_min_gap(plan, a, rb_day, rb_day, days_in_month):
            return
        _add_entry(plan, rb_day, a.id, ShiftType.ON_CALL)
        oncall_assigned[a.id] += 1

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
            # Toleranz lockern: Auto-Zielgrenze ignorieren; explizites
            # Maximum und Mindestabstand bleiben harte Grenzen
            # (Tag bleibt sonst offen)
            available = [
                a for a in active
                if not _works_on(plan, a.id, day)
                and not is_unavailable(a, day, year, month)
                and not exceeds_consecutive(plan, a.id, day)
                and not _violates_min_gap(plan, a, day, day, days_in_month)
                and (a.constraints.max_shifts is None
                     or assigned[a.id] + weight <= a.constraints.max_shifts)
            ]
        if not available:
            continue

        chosen = pick(available)
        _add_entry(plan, day, chosen.id, needed)
        assigned[chosen.id] += weight
        try_attach_oncall(chosen, day)

    # 5. Rufbereitschaft: jeder Tag eine Person, Ziel je Helfer = genau die
    #    eigene (gewichtete) Dienstzahl (Gleichstand); nie am eigenen
    #    Diensttag. Angehaengte RB-Bloecke (oncall_attach) sind schon vergeben
    oncall_target = {a.id: assigned[a.id] for a in active}

    def oncall_candidates(day: int, pool, respect_target: bool = True) -> list:
        result = []
        for a in pool:
            if _works_on(plan, a.id, day):
                continue
            if is_unavailable(a, day, year, month):
                continue
            if exceeds_consecutive(plan, a.id, day, ON_CALL_KINDS):
                continue
            if _violates_min_gap(plan, a, day, day, days_in_month):
                continue
            # Gleichstand RB = Dienste: +0,5 erlaubt das Aufrunden bei
            # halben Diensten, mehr nicht
            if respect_target and oncall_assigned[a.id] + 1 > oncall_target[a.id] + 0.5:
                continue
            result.append(a)
        return result

    def oncall_pick(pool: list):
        # Wer am weitesten unter seinem RB-Ziel liegt, kommt zuerst
        return min(
            pool,
            key=lambda a: (oncall_assigned[a.id] - oncall_target[a.id], rng.random()),
        )

    # Blockvergabe fuer die Rufbereitschaft (weite Anreise)
    rng.shuffle(block_assistants)
    for a in block_assistants:
        block_len = a.constraints.min_block_days
        while oncall_assigned[a.id] + block_len <= oncall_target[a.id] + 0.5:
            starts = []
            for start in range(1, days_in_month - block_len + 2):
                days = range(start, start + block_len)
                if not all(_needs_oncall(plan, d) for d in days):
                    continue
                if any(_works_on(plan, a.id, d) for d in days):
                    continue
                if any(is_unavailable(a, d, year, month) for d in days):
                    continue
                run = _run_length_if_assigned(
                    plan, a.id, start, start + block_len - 1, ON_CALL_KINDS
                )
                if run > a.constraints.max_consecutive_days:
                    continue
                if _violates_min_gap(plan, a, start, start + block_len - 1,
                                     days_in_month):
                    continue
                starts.append(start)
            if not starts:
                break
            start = rng.choice(starts)
            for d in range(start, start + block_len):
                _add_entry(plan, d, a.id, ShiftType.ON_CALL)
            oncall_assigned[a.id] += block_len

    open_oncall_days = [d for d in range(1, days_in_month + 1) if _needs_oncall(plan, d)]
    rng.shuffle(open_oncall_days)
    for day in open_oncall_days:
        available = oncall_candidates(day, single_assistants)
        if not available:
            available = oncall_candidates(day, block_assistants)
        if not available:
            # Zielgrenze lockern, damit kein Tag ohne RB bleibt; der
            # Gleichstand wird anschliessend in Schritt 6 repariert
            available = oncall_candidates(day, active, respect_target=False)
        if not available:
            continue

        chosen = oncall_pick(available)
        _add_entry(plan, day, chosen.id, ShiftType.ON_CALL)
        oncall_assigned[chosen.id] += 1

    # 6. Ausgleichsrunde fuer den Gleichstand RB = Dienste: Helfer ueber
    #    ihrem RB-Ziel geben generierte, nicht fixierte RB-Tage an Helfer
    #    unter dem Ziel ab, sofern alle Regeln es zulassen
    def _oncall_entry(day: int, assistant_id: str) -> ShiftEntry | None:
        return next(
            (e for e in plan.schedule.get(day, [])
             if e.assistant_id == assistant_id and e.shift_type == ShiftType.ON_CALL),
            None,
        )

    moved = True
    while moved:
        moved = False
        givers = [a for a in active if oncall_assigned[a.id] - oncall_target[a.id] > 0.5]
        for giver in givers:
            for day in range(1, days_in_month + 1):
                entry = _oncall_entry(day, giver.id)
                if entry is None or not entry.generated or entry.locked:
                    continue
                # Probeweise entfernen, damit Folge-/Abstandspruefungen
                # fuer den Nehmer den echten Zustand sehen
                plan.schedule[day].remove(entry)
                takers = oncall_candidates(day, [
                    a for a in active
                    if oncall_target[a.id] - oncall_assigned[a.id] > 0.5
                ])
                if takers:
                    taker = oncall_pick(takers)
                    _add_entry(plan, day, taker.id, ShiftType.ON_CALL)
                    oncall_assigned[taker.id] += 1
                    oncall_assigned[giver.id] -= 1
                    moved = True
                    break
                plan.schedule[day].append(entry)
            if moved:
                break

    return plan
