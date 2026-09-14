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
eingeplant (weite Anreise). Mit oncall_attach ("before"/"after"/"both") haengt
der Generator die Rufbereitschaft als Block direkt vor, nach bzw. auf beide
Seiten verteilt an den Dienstblock, damit die Person am Stueck vor Ort ist.
Die Gesamtzahl der angehaengten RB-Tage bleibt dabei immer so gross wie der
Dienstblock - auch bei "both" - damit RB = Dienste aufgeht.
min_gap_days ist der Mindestabstand in freien Tagen zwischen zwei
Einsatzbloecken derselben Person (Dienst und RB zusammen gezaehlt) - eine
harte Regel, die der Generator nie unterschreitet.

Kandidaten (Stufe 2): Tage koennen mehrere manuelle Vorschlaege fuer
denselben Dienst/RB tragen (ShiftEntry.candidate). Der Generator waehlt vor
der normalen Fuellung einen zulaessigen Kandidaten (chosen=True); nicht
gewaehlte Kandidaten zaehlen nirgends mit (is_effective).

Freiwunsch-Kontingent (Stufe 2): Block-Tage sind Wuensche. Ohne Kontingent
(free_wish_quota=None) bleiben sie hart wie Urlaub. Mit Kontingent N haben
die chronologisch ersten N Block-Tage des Monats Vorrang (hart), weitere
Nachrang: Bleibt ein Tag sonst offen, darf ein Nachrang-Wunsch ueberplant
werden - das wird als Conflict gemeldet (Dialog in der UI). Urlaub, hartes
Max, Folgen und Mindestabstand werden auch dabei nie verletzt.
"""
from __future__ import annotations
import random
import calendar
from dataclasses import dataclass, field
from datetime import date
from models import (
    MonthPlan, ShiftEntry, ShiftType, DUTY_TYPES, is_duty, is_effective,
    blocked_days,
)

ON_CALL_KINDS = (ShiftType.ON_CALL,)


@dataclass
class ConflictOption:
    assistant_id: str | None    # None = Tag offen lassen
    overrides_wish: bool
    label: str


@dataclass
class Conflict:
    day: int
    kind: str                   # "dienst" | "rb"
    options: list[ConflictOption]
    proposal: int               # Index des empfohlenen Vorschlags
    applied: int = 0            # Index der tatsaechlich angewandten Option


@dataclass
class GenerationResult:
    plan: MonthPlan
    conflicts: list[Conflict] = field(default_factory=list)


def attach_spans(attach: str, start: int, block_len: int) -> list[range]:
    """Tage fuer die angehaengte Rufbereitschaft rund um den Dienstblock
    start .. start + block_len - 1.

    "before"/"after": ein gleich langer RB-Block davor bzw. danach.
    "both": derselbe RB-Block, aufgeteilt auf beide Seiten (bei ungerader
    Laenge liegt der laengere Teil hinten). Die Summe bleibt block_len,
    damit die Gleichung "RB-Tage = Dienste" weiter aufgeht.
    """
    if attach == "before":
        return [range(start - block_len, start)]
    if attach == "after":
        return [range(start + block_len, start + 2 * block_len)]
    if attach == "both":
        before_len = block_len // 2
        after_len = block_len - before_len
        spans = []
        if before_len:
            spans.append(range(start - before_len, start))
        if after_len:
            end = start + block_len
            spans.append(range(end, end + after_len))
        return spans
    return []


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


def wish_priority(assistant, day: int, year: int, month: int) -> str | None:
    """Rang eines Block-Tags (Freiwunsch): "vorrang" (hart), "nachrang"
    (darf im Konfliktfall ueberplant werden) oder None (kein Block).

    Ohne Kontingent (free_wish_quota=None) sind alle Wuensche Vorrang -
    das bisherige harte Verhalten. Mit Kontingent N haben die chronologisch
    ersten N Block-Tage des Monats Vorrang, alle weiteren Nachrang."""
    if not is_blocked(assistant, day, year, month):
        return None
    quota = assistant.constraints.free_wish_quota
    if quota is None:
        return "vorrang"
    month_blocked = sorted(
        d for d in blocked_days(assistant.constraints)
        if d.year == year and d.month == month
    )
    return "vorrang" if month_blocked.index(date(year, month, day)) < quota else "nachrang"


def wish_overhang(assistant, year: int, month: int) -> int:
    """Anzahl der Nachrang-Wuensche dieses Monats (Wuensche ueber dem
    Kontingent). 0, wenn kein Kontingent gesetzt ist."""
    quota = assistant.constraints.free_wish_quota
    if quota is None:
        return 0
    count = sum(
        1 for d in blocked_days(assistant.constraints)
        if d.year == year and d.month == month
    )
    return max(0, count - quota)


def shift_weight(shift_type: ShiftType) -> float:
    return 0.5 if shift_type in (ShiftType.HALF_MORNING, ShiftType.HALF_AFTERNOON) else 1.0


def _works_on(plan: MonthPlan, assistant_id: str, day: int,
              kinds: tuple[ShiftType, ...] | None = None) -> bool:
    """kinds=None: irgendein wirksamer Eintrag (Tages-Exklusivitaet),
    sonst nur Eintraege der angegebenen Dienstarten. Nicht gewaehlte
    Kandidaten sind nur Vorschlaege und zaehlen nicht."""
    return any(
        e.assistant_id == assistant_id and is_effective(e)
        and (kinds is None or e.shift_type in kinds)
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
    Rufbereitschafts-Eintraege und nicht gewaehlte Kandidaten zaehlen hier
    nicht als Abdeckung."""
    entries = [
        e for e in plan.schedule.get(day, [])
        if is_duty(e.shift_type) and is_effective(e)
    ]
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
    """True, wenn an diesem Tag noch keine wirksame Rufbereitschaft vergeben ist."""
    return not any(
        e.shift_type == ShiftType.ON_CALL and is_effective(e)
        for e in plan.schedule.get(day, [])
    )


def _add_entry(plan: MonthPlan, day: int, assistant_id: str, shift_type: ShiftType) -> None:
    plan.schedule.setdefault(day, []).append(
        ShiftEntry(assistant_id=assistant_id, shift_type=shift_type, generated=True)
    )


def generate(plan: MonthPlan, seed: int | None = None,
             resolver=None) -> GenerationResult:
    """Wuerfelt den Plan. resolver: optionaler Callable(Conflict) ->
    ConflictOption, der Konflikte entscheidet (Dialog-Wiederholungslauf);
    ohne Resolver wird jeweils der Vorschlag angewendet."""
    rng = random.Random(seed) if seed is not None else random.Random()
    year, month = plan.year, plan.month
    days_in_month = calendar.monthrange(year, month)[1]
    conflicts: list[Conflict] = []

    # 1. Nicht fixierte Zufalls-Eintraege entfernen (Neuwuerfeln); nicht
    #    fixierte Kandidaten-Wahlen zuruecksetzen (werden neu getroffen)
    for day in list(plan.schedule.keys()):
        plan.schedule[day] = [
            e for e in plan.schedule[day] if not e.generated or e.locked
        ]
        for e in plan.schedule[day]:
            if e.candidate and e.chosen and not e.locked:
                e.chosen = False
        if not plan.schedule[day]:
            del plan.schedule[day]

    active = [a for a in plan.assistants if a.active]
    if not active:
        return GenerationResult(plan)
    by_id = {a.id: a for a in active}

    # 2. Zielzahlen und bereits vergebene Dienste (VOLL=1, VM/NM=0,5);
    #    Rufbereitschaften zaehlen separat. Nicht gewaehlte Kandidaten
    #    zaehlen nicht mit
    assigned = {a.id: 0.0 for a in active}
    oncall_assigned = {a.id: 0 for a in active}
    for entries in plan.schedule.values():
        for e in entries:
            if e.assistant_id not in assigned or not is_effective(e):
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

    def _wish_conflict(day: int, kind: str, pool: list, place) -> None:
        """Konfliktstufe: Tag ist nur durch Ueberplanen eines Nachrang-
        Freiwunschs besetzbar. pool ist nach Vorschlagsguete sortiert;
        ohne Resolver wird der Vorschlag angewendet, sonst entscheidet er.
        Der Konflikt wird fuer den Dialog gemeldet."""
        options = [
            ConflictOption(a.id, True, f"{a.name} (ueberplant Freiwunsch)")
            for a in pool
        ]
        options.append(ConflictOption(None, False, "Tag offen lassen"))
        conflict = Conflict(day=day, kind=kind, options=options, proposal=0)
        selected = options[0] if resolver is None else resolver(conflict)
        if selected not in options:
            selected = options[conflict.proposal]
        conflict.applied = options.index(selected)
        if selected.assistant_id is not None:
            place(by_id[selected.assistant_id])
        conflicts.append(conflict)

    def _rb_span_free(a, rb_days: range) -> bool:
        """Passt ein angehaengter RB-Block auf diese Tage?"""
        if rb_days[0] < 1 or rb_days[-1] > days_in_month:
            return False
        if not all(_needs_oncall(plan, d) for d in rb_days):
            return False
        if any(_works_on(plan, a.id, d) for d in rb_days):
            return False
        if any(is_unavailable(a, d, year, month) for d in rb_days):
            return False
        rb_run = _run_length_if_assigned(
            plan, a.id, rb_days[0], rb_days[-1], ON_CALL_KINDS
        )
        return rb_run <= a.constraints.max_consecutive_days

    # 2b. Kandidatenwahl Dienst: Tage mit mehreren manuellen VOLL-Vorschlaegen
    #     bekommen vor allem anderen einen Gewaehlten (chosen=True) - nach den
    #     ueblichen Fairness-Regeln; harte Regeln gelten auch fuer Kandidaten
    def _candidate_entries(day: int, shift_type: ShiftType) -> list[ShiftEntry]:
        return [
            e for e in plan.schedule.get(day, [])
            if e.candidate and not e.chosen and e.shift_type == shift_type
            and e.assistant_id in by_id
        ]

    def _feasible_duty_candidate(a, day: int) -> bool:
        return (
            not _works_on(plan, a.id, day)
            and not is_unavailable(a, day, year, month)
            and not exceeds_consecutive(plan, a.id, day)
            and not _violates_min_gap(plan, a, day, day, days_in_month)
        )

    for day in range(1, days_in_month + 1):
        if _day_needs(plan, day) != ShiftType.FULL:
            continue
        entries = _candidate_entries(day, ShiftType.FULL)
        if not entries:
            continue
        pool = [by_id[e.assistant_id] for e in entries
                if _feasible_duty_candidate(by_id[e.assistant_id], day)]
        # Kandidaten sind ausdrueckliche Wuensche des Planers: die weiche
        # Auto-Zielgrenze zaehlt nur zur Bevorzugung, ein explizites Max
        # bleibt hart
        preferred = [a for a in pool if assigned[a.id] + 1.0 <= duty_cap(a)]
        pool = preferred or [
            a for a in pool
            if a.constraints.max_shifts is None
            or assigned[a.id] + 1.0 <= a.constraints.max_shifts
        ]
        if not pool:
            continue
        chosen_assistant = pick(pool)
        for e in entries:
            if e.assistant_id == chosen_assistant.id:
                e.chosen = True
                break
        assigned[chosen_assistant.id] += 1.0

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
                rb_spans = attach_spans(attach, start, block_len)
                if not all(_rb_span_free(a, rb_days) for rb_days in rb_spans):
                    continue
                for rb_days in rb_spans:
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
            for rb_days in attach_spans(attach, start, block_len):
                for d in rb_days:
                    _add_entry(plan, d, a.id, ShiftType.ON_CALL)
                    oncall_assigned[a.id] += 1

    def try_attach_oncall(a, day: int) -> None:
        """Haengt fuer Helfer mit oncall_attach die Rufbereitschaft direkt
        an einen einzeln vergebenen Diensttag an (best effort).

        Bei "both" werden beide Seiten versucht; da RB-Tage die Dienstzahl
        nicht ueberschreiten duerfen, bleibt es bei einem einzelnen
        Diensttag in der Regel bei einer Seite.
        """
        attach = a.constraints.oncall_attach
        if attach == "before":
            rb_days = [day - 1]
        elif attach == "after":
            rb_days = [day + 1]
        elif attach == "both":
            rb_days = [day - 1, day + 1]
        else:
            return

        for rb_day in rb_days:
            if not 1 <= rb_day <= days_in_month:
                continue
            if oncall_assigned[a.id] + 1 > assigned[a.id] + 0.5:
                continue
            if not _needs_oncall(plan, rb_day):
                continue
            if _works_on(plan, a.id, rb_day):
                continue
            if is_unavailable(a, rb_day, year, month):
                continue
            if exceeds_consecutive(plan, a.id, rb_day, ON_CALL_KINDS):
                continue
            if _violates_min_gap(plan, a, rb_day, rb_day, days_in_month):
                continue
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
            # Konfliktstufe: Nachrang-Freiwunsch ueberplanen. Urlaub,
            # Vorrang-Wuensche und harte Grenzen bleiben unantastbar
            pool = [
                a for a in active
                if wish_priority(a, day, year, month) == "nachrang"
                and not is_on_vacation(a, day, year, month)
                and not _works_on(plan, a.id, day)
                and not exceeds_consecutive(plan, a.id, day)
                and not _violates_min_gap(plan, a, day, day, days_in_month)
                and (a.constraints.max_shifts is None
                     or assigned[a.id] + weight <= a.constraints.max_shifts)
            ]
            if pool:
                # Vorschlag: groesster Wunsch-Ueberhang, dann wenigste Dienste
                pool.sort(key=lambda a: (
                    -wish_overhang(a, year, month), assigned[a.id], rng.random()
                ))

                def place_duty(a, d=day, w=weight, n=needed):
                    _add_entry(plan, d, a.id, n)
                    assigned[a.id] += w

                _wish_conflict(day, "dienst", pool, place_duty)
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

    # 5b. Kandidatenwahl Rufbereitschaft: Tage mit mehreren manuellen
    #     RB-Vorschlaegen bekommen zuerst einen Gewaehlten (nie am eigenen
    #     wirksamen Diensttag)
    for day in range(1, days_in_month + 1):
        if not _needs_oncall(plan, day):
            continue
        entries = _candidate_entries(day, ShiftType.ON_CALL)
        if not entries:
            continue
        pool = [
            by_id[e.assistant_id] for e in entries
            if not _works_on(plan, e.assistant_id, day)
            and not is_unavailable(by_id[e.assistant_id], day, year, month)
            and not exceeds_consecutive(plan, e.assistant_id, day, ON_CALL_KINDS)
            and not _violates_min_gap(plan, by_id[e.assistant_id], day, day,
                                      days_in_month)
        ]
        # RB-Ziel nur zur Bevorzugung, nicht als Ausschluss - der Tag traegt
        # ausdrueckliche Vorschlaege
        preferred = [
            a for a in pool
            if oncall_assigned[a.id] + 1 <= oncall_target[a.id] + 0.5
        ]
        pool = preferred or pool
        if not pool:
            continue
        chosen_assistant = oncall_pick(pool)
        for e in entries:
            if e.assistant_id == chosen_assistant.id:
                e.chosen = True
                break
        oncall_assigned[chosen_assistant.id] += 1

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
            # Konfliktstufe wie beim Dienst: Nachrang-Freiwunsch ueberplanen
            pool = [
                a for a in active
                if wish_priority(a, day, year, month) == "nachrang"
                and not is_on_vacation(a, day, year, month)
                and not _works_on(plan, a.id, day)
                and not exceeds_consecutive(plan, a.id, day, ON_CALL_KINDS)
                and not _violates_min_gap(plan, a, day, day, days_in_month)
            ]
            if pool:
                pool.sort(key=lambda a: (
                    -wish_overhang(a, year, month),
                    oncall_assigned[a.id] - oncall_target[a.id],
                    rng.random(),
                ))

                def place_oncall(a, d=day):
                    _add_entry(plan, d, a.id, ShiftType.ON_CALL)
                    oncall_assigned[a.id] += 1

                _wish_conflict(day, "rb", pool, place_oncall)
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

    return GenerationResult(plan, conflicts)
