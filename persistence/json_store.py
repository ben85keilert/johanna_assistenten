from __future__ import annotations
import json
import sys
from datetime import date
from pathlib import Path

from models.plan import MonthPlan
from models.assistant import (
    Assistant, AssistantConstraints, absence_days, set_absence_days
)
from models.shift import ShiftEntry, ShiftType
from .migrations import (
    migrate_team,
    migrate_plan,
    CURRENT_TEAM_VERSION,
    CURRENT_PLAN_VERSION,
)


def _base_dir() -> Path:
    # Gefrorene .exe (PyInstaller): Daten neben der Executable,
    # sonst im Projektstamm - unabhaengig vom Arbeitsverzeichnis
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


DATA_DIR = _base_dir() / "data"
PLANS_DIR = DATA_DIR / "plans"
TEAM_FILE = DATA_DIR / "team.json"


def _constraints_to_dict(c: AssistantConstraints, include_target: bool = True) -> dict:
    result = {
        "assistant_id": c.assistant_id,
        "unavailable_dates": [d.isoformat() for d in c.unavailable_dates],
        "vacation_ranges": [
            [start.isoformat(), end.isoformat()] for start, end in c.vacation_ranges
        ],
        "blocked_dates": [d.isoformat() for d in c.blocked_dates],
        "blocked_ranges": [
            [start.isoformat(), end.isoformat()] for start, end in c.blocked_ranges
        ],
        "max_consecutive_days": c.max_consecutive_days,
        "min_block_days": c.min_block_days,
    }
    if include_target:
        result["min_shifts"] = c.min_shifts
        result["max_shifts"] = c.max_shifts
    return result


def _is_default_constraints(c: AssistantConstraints) -> bool:
    return (
        not c.unavailable_dates
        and not c.vacation_ranges
        and not c.blocked_dates
        and not c.blocked_ranges
        and c.max_consecutive_days == 3
        and c.min_block_days == 1
    )


def _constraints_from_dict(c_data: dict, assistant_id: str = "") -> AssistantConstraints:
    return AssistantConstraints(
        assistant_id=c_data.get("assistant_id", assistant_id),
        unavailable_dates=[
            date.fromisoformat(d) for d in c_data.get("unavailable_dates", [])
        ],
        vacation_ranges=[
            (date.fromisoformat(start), date.fromisoformat(end))
            for start, end in c_data.get("vacation_ranges", [])
        ],
        blocked_dates=[
            date.fromisoformat(d) for d in c_data.get("blocked_dates", [])
        ],
        blocked_ranges=[
            (date.fromisoformat(start), date.fromisoformat(end))
            for start, end in c_data.get("blocked_ranges", [])
        ],
        max_consecutive_days=c_data.get("max_consecutive_days", 3),
        min_block_days=c_data.get("min_block_days", 1),
        min_shifts=c_data.get("min_shifts"),
        max_shifts=c_data.get("max_shifts"),
    )


def _entry_to_dict(e: ShiftEntry) -> dict:
    return {
        "assistant_id": e.assistant_id,
        "shift_type": e.shift_type.value,
        "locked": e.locked,
        "generated": e.generated,
    }


def _entry_from_dict(e_data: dict) -> ShiftEntry:
    return ShiftEntry(
        assistant_id=e_data.get("assistant_id", ""),
        shift_type=ShiftType(e_data.get("shift_type", "FULL")),
        locked=e_data.get("locked", False),
        generated=e_data.get("generated", False),
    )


def _schedule_to_dict(schedule: dict[int, list[ShiftEntry]]) -> dict:
    return {
        str(day): [_entry_to_dict(e) for e in entries]
        for day, entries in schedule.items()
    }


def _schedule_from_dict(data: dict) -> dict[int, list[ShiftEntry]]:
    return {
        int(day_str): [_entry_from_dict(e) for e in entries]
        for day_str, entries in data.items()
    }


def _assistant_to_dict(a: Assistant, with_constraints: bool) -> dict:
    result = {
        "id": a.id,
        "name": a.name,
        "color": a.color,
        "active": a.active,
    }
    if with_constraints:
        result["constraints"] = _constraints_to_dict(a.constraints)
    return result


# --- Vollstaendiger Plan als einzelne Datei (Datei > Oeffnen/Speichern) ---

def save(plan: MonthPlan, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "version": CURRENT_PLAN_VERSION,
        "year": plan.year,
        "month": plan.month,
        "schedule": _schedule_to_dict(plan.schedule),
        "assistants": [_assistant_to_dict(a, with_constraints=True) for a in plan.assistants],
        "seed": plan.seed,
        "created_at": plan.created_at,
        "modified_at": plan.modified_at,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load(path: str | Path) -> MonthPlan:
    path = Path(path)
    with open(path, "r", encoding="utf-8") as f:
        data = migrate_plan(json.load(f))

    assistants = []
    for a_data in data.get("assistants", []):
        constraints = _constraints_from_dict(
            a_data.get("constraints", {}), a_data.get("id", "")
        )
        assistants.append(
            Assistant(
                id=a_data.get("id", ""),
                name=a_data.get("name", ""),
                color=a_data.get("color", "#000000"),
                constraints=constraints,
                active=a_data.get("active", True),
            )
        )

    return MonthPlan(
        year=data.get("year", 2026),
        month=data.get("month", 1),
        schedule=_schedule_from_dict(data.get("schedule", {})),
        assistants=assistants,
        seed=data.get("seed"),
        created_at=data.get("created_at", ""),
        modified_at=data.get("modified_at", ""),
    )


# --- Team (monatsuebergreifend) ---

def team_path() -> Path:
    return TEAM_FILE


def save_team(assistants: list[Assistant]) -> None:
    # Personenbezogene Constraints (Urlaube, Einzeltage, Max/Min) leben
    # monatsuebergreifend hier; nur die Soll-Dienste (min/max) gehoeren
    # zum Monatsplan
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "version": CURRENT_TEAM_VERSION,
        "assistants": [
            {
                **_assistant_to_dict(a, with_constraints=False),
                "constraints": _constraints_to_dict(a.constraints, include_target=False),
            }
            for a in assistants
        ],
    }
    with open(TEAM_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_team() -> list[Assistant]:
    if not TEAM_FILE.exists():
        return []

    with open(TEAM_FILE, "r", encoding="utf-8") as f:
        data = migrate_team(json.load(f))

    assistants = []
    for a_data in data.get("assistants", []):
        if isinstance(a_data, dict):
            constraints = _constraints_from_dict(
                a_data.get("constraints", {}), a_data.get("id", "")
            )
            assistants.append(
                Assistant(
                    id=a_data.get("id", ""),
                    name=a_data.get("name", ""),
                    color=a_data.get("color", "#000000"),
                    constraints=constraints,
                    active=a_data.get("active", True),
                )
            )
    return assistants


# --- Monatsplaene (automatische Ablage unter data/plans/) ---

def plan_path(year: int, month: int) -> Path:
    return PLANS_DIR / f"plan_{year}_{month:02d}.json"


def save_plan(plan: MonthPlan) -> None:
    PLANS_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "version": CURRENT_PLAN_VERSION,
        "year": plan.year,
        "month": plan.month,
        "schedule": _schedule_to_dict(plan.schedule),
        # Nur die monatsbezogenen Soll-Dienste; alle uebrigen Constraints
        # liegen monatsuebergreifend in team.json
        "targets": {
            a.id: {"min": a.constraints.min_shifts, "max": a.constraints.max_shifts}
            for a in plan.assistants
        },
        "seed": plan.seed,
        "created_at": plan.created_at,
        "modified_at": plan.modified_at,
    }
    with open(plan_path(plan.year, plan.month), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_plan(year: int, month: int, assistants: list[Assistant]) -> MonthPlan | None:
    """Laedt den Monatsplan. Die uebergebenen Assistenten (aus team.json)
    behalten ihre Constraints; nur die Soll-Dienste (min/max) kommen aus
    der Monatsdatei."""
    path = plan_path(year, month)
    if not path.exists():
        return None

    with open(path, "r", encoding="utf-8") as f:
        data = migrate_plan(json.load(f))

    targets = data.get("targets", {})

    # Backfill fuer alte v2-Dateien: Constraints aus der Monatsdatei einmalig
    # ins (noch leere) Team uebernehmen; gespeichert wird ab dann in team.json
    legacy_by_id = {
        c_data.get("assistant_id", ""): c_data
        for c_data in data.get("legacy_constraints", [])
    }

    for assistant in assistants:
        legacy = legacy_by_id.get(assistant.id)
        if legacy:
            legacy_constraints = _constraints_from_dict(legacy, assistant.id)
            # Max/Min nur uebernehmen, solange das Team noch Defaults hat
            if _is_default_constraints(assistant.constraints):
                assistant.constraints.max_consecutive_days = legacy_constraints.max_consecutive_days
                assistant.constraints.min_block_days = legacy_constraints.min_block_days
            # Datumsbasierte Abwesenheiten additiv vereinigen: Daten sind
            # absolut, so geht aus keiner alten Monatsdatei etwas verloren
            merged = absence_days(assistant.constraints) | absence_days(legacy_constraints)
            set_absence_days(assistant.constraints, merged)
        target = targets.get(assistant.id)
        if isinstance(target, dict):
            assistant.constraints.min_shifts = target.get("min")
            assistant.constraints.max_shifts = target.get("max")
        else:
            # Defensiv: alter int-Wert trotz Migration, oder Helfer ohne Eintrag
            assistant.constraints.min_shifts = target
            assistant.constraints.max_shifts = target

    return MonthPlan(
        year=year,
        month=month,
        schedule=_schedule_from_dict(data.get("schedule", {})),
        assistants=assistants,
        seed=data.get("seed"),
        created_at=data.get("created_at", ""),
        modified_at=data.get("modified_at", ""),
    )
