from __future__ import annotations
import json
import sys
from datetime import date
from pathlib import Path

from models.plan import MonthPlan
from models.assistant import Assistant, AssistantConstraints
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


def _constraints_to_dict(c: AssistantConstraints) -> dict:
    return {
        "assistant_id": c.assistant_id,
        "unavailable_dates": [d.isoformat() for d in c.unavailable_dates],
        "vacation_ranges": [
            [start.isoformat(), end.isoformat()] for start, end in c.vacation_ranges
        ],
        "max_consecutive_days": c.max_consecutive_days,
        "min_block_days": c.min_block_days,
        "target_shifts": c.target_shifts,
    }


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
        max_consecutive_days=c_data.get("max_consecutive_days", 3),
        min_block_days=c_data.get("min_block_days", 1),
        target_shifts=c_data.get("target_shifts"),
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
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "version": CURRENT_TEAM_VERSION,
        "assistants": [_assistant_to_dict(a, with_constraints=False) for a in assistants],
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
            assistants.append(
                Assistant(
                    id=a_data.get("id", ""),
                    name=a_data.get("name", ""),
                    color=a_data.get("color", "#000000"),
                    constraints=AssistantConstraints(assistant_id=a_data.get("id", "")),
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
        "constraints": [_constraints_to_dict(a.constraints) for a in plan.assistants],
        "seed": plan.seed,
        "created_at": plan.created_at,
        "modified_at": plan.modified_at,
    }
    with open(plan_path(plan.year, plan.month), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_plan(year: int, month: int, assistants: list[Assistant]) -> MonthPlan | None:
    path = plan_path(year, month)
    if not path.exists():
        return None

    with open(path, "r", encoding="utf-8") as f:
        data = migrate_plan(json.load(f))

    constraints_by_id = {
        c_data.get("assistant_id", ""): _constraints_from_dict(c_data)
        for c_data in data.get("constraints", [])
    }

    loaded_assistants = []
    for assistant in assistants:
        constraints = constraints_by_id.get(
            assistant.id, AssistantConstraints(assistant_id=assistant.id)
        )
        loaded_assistants.append(
            Assistant(
                id=assistant.id,
                name=assistant.name,
                color=assistant.color,
                constraints=constraints,
                active=assistant.active,
            )
        )

    return MonthPlan(
        year=year,
        month=month,
        schedule=_schedule_from_dict(data.get("schedule", {})),
        assistants=loaded_assistants,
        seed=data.get("seed"),
        created_at=data.get("created_at", ""),
        modified_at=data.get("modified_at", ""),
    )
