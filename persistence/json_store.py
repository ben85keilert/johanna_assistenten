from __future__ import annotations
import json
from datetime import date, datetime
from pathlib import Path

from models.plan import MonthPlan
from models.assistant import Assistant, AssistantConstraints
from models.shift import ShiftEntry, ShiftType

DATA_DIR = Path("data")
PLANS_DIR = DATA_DIR / "plans"
TEAM_FILE = DATA_DIR / "team.json"


class PlanEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, date):
            return obj.isoformat()
        elif isinstance(obj, ShiftType):
            return obj.value
        elif isinstance(obj, ShiftEntry):
            return {
                "assistant_id": obj.assistant_id,
                "shift_type": obj.shift_type.value,
                "locked": obj.locked,
            }
        elif isinstance(obj, AssistantConstraints):
            return {
                "assistant_id": obj.assistant_id,
                "unavailable_dates": [d.isoformat() for d in obj.unavailable_dates],
                "vacation_ranges": [
                    [start.isoformat(), end.isoformat()]
                    for start, end in obj.vacation_ranges
                ],
                "max_consecutive_days": obj.max_consecutive_days,
                "target_shifts": obj.target_shifts,
            }
        elif isinstance(obj, Assistant):
            return {
                "id": obj.id,
                "name": obj.name,
                "color": obj.color,
                "active": obj.active,
                "constraints": json.loads(json.dumps(obj.constraints, cls=PlanEncoder)),
            }
        elif isinstance(obj, MonthPlan):
            schedule_dict = {}
            for day, entries in obj.schedule.items():
                schedule_dict[str(day)] = [
                    json.loads(json.dumps(e, cls=PlanEncoder)) for e in entries
                ]
            return {
                "version": 1,
                "year": obj.year,
                "month": obj.month,
                "schedule": schedule_dict,
                "assistants": [
                    json.loads(json.dumps(a, cls=PlanEncoder)) for a in obj.assistants
                ],
                "seed": obj.seed,
                "created_at": obj.created_at,
                "modified_at": obj.modified_at,
            }
        return super().default(obj)


def save(plan: MonthPlan, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(plan, f, cls=PlanEncoder, indent=2, ensure_ascii=False)


def load(path: str | Path) -> MonthPlan:
    path = Path(path)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assistants = []
    for a_data in data.get("assistants", []):
        c_data = a_data.get("constraints", {})
        constraints = AssistantConstraints(
            assistant_id=c_data.get("assistant_id", ""),
            unavailable_dates=[
                date.fromisoformat(d) for d in c_data.get("unavailable_dates", [])
            ],
            vacation_ranges=[
                (date.fromisoformat(start), date.fromisoformat(end))
                for start, end in c_data.get("vacation_ranges", [])
            ],
            max_consecutive_days=c_data.get("max_consecutive_days", 3),
            target_shifts=c_data.get("target_shifts"),
        )
        assistant = Assistant(
            id=a_data.get("id", ""),
            name=a_data.get("name", ""),
            color=a_data.get("color", "#000000"),
            constraints=constraints,
            active=a_data.get("active", True),
        )
        assistants.append(assistant)

    schedule = {}
    for day_str, entries_data in data.get("schedule", {}).items():
        day = int(day_str)
        entries = []
        for e_data in entries_data:
            entry = ShiftEntry(
                assistant_id=e_data.get("assistant_id", ""),
                shift_type=ShiftType(e_data.get("shift_type", "FULL")),
                locked=e_data.get("locked", False),
            )
            entries.append(entry)
        schedule[day] = entries

    plan = MonthPlan(
        year=data.get("year", 2026),
        month=data.get("month", 1),
        schedule=schedule,
        assistants=assistants,
        seed=data.get("seed"),
        created_at=data.get("created_at", ""),
        modified_at=data.get("modified_at", ""),
    )
    return plan


def team_path() -> Path:
    return TEAM_FILE


def plan_path(year: int, month: int) -> Path:
    return PLANS_DIR / f"plan_{year}_{month:02d}.json"


class TeamEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Assistant):
            return {
                "id": obj.id,
                "name": obj.name,
                "color": obj.color,
                "active": obj.active,
            }
        return super().default(obj)


def save_team(assistants: list[Assistant]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(TEAM_FILE, "w", encoding="utf-8") as f:
        json.dump(assistants, f, cls=TeamEncoder, indent=2, ensure_ascii=False)


def load_team() -> list[Assistant]:
    if not TEAM_FILE.exists():
        return []

    with open(TEAM_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    assistants = []
    for a_data in data:
        if isinstance(a_data, dict):
            constraints = AssistantConstraints(assistant_id=a_data.get("id", ""))
            assistant = Assistant(
                id=a_data.get("id", ""),
                name=a_data.get("name", ""),
                color=a_data.get("color", "#000000"),
                constraints=constraints,
                active=a_data.get("active", True),
            )
            assistants.append(assistant)

    return assistants


class PlanOnlyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, date):
            return obj.isoformat()
        elif isinstance(obj, ShiftType):
            return obj.value
        elif isinstance(obj, ShiftEntry):
            return {
                "assistant_id": obj.assistant_id,
                "shift_type": obj.shift_type.value,
                "locked": obj.locked,
            }
        elif isinstance(obj, AssistantConstraints):
            return {
                "assistant_id": obj.assistant_id,
                "unavailable_dates": [d.isoformat() for d in obj.unavailable_dates],
                "vacation_ranges": [
                    [start.isoformat(), end.isoformat()]
                    for start, end in obj.vacation_ranges
                ],
                "max_consecutive_days": obj.max_consecutive_days,
                "target_shifts": obj.target_shifts,
            }
        elif isinstance(obj, MonthPlan):
            schedule_dict = {}
            for day, entries in obj.schedule.items():
                schedule_dict[str(day)] = [
                    json.loads(json.dumps(e, cls=PlanOnlyEncoder)) for e in entries
                ]
            return {
                "version": 1,
                "year": obj.year,
                "month": obj.month,
                "schedule": schedule_dict,
                "constraints": [
                    json.loads(json.dumps(a.constraints, cls=PlanOnlyEncoder))
                    for a in obj.assistants
                ],
                "seed": obj.seed,
                "created_at": obj.created_at,
                "modified_at": obj.modified_at,
            }
        return super().default(obj)


def save_plan(plan: MonthPlan) -> None:
    PLANS_DIR.mkdir(parents=True, exist_ok=True)
    path = plan_path(plan.year, plan.month)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(plan, f, cls=PlanOnlyEncoder, indent=2, ensure_ascii=False)


def load_plan(year: int, month: int, assistants: list[Assistant]) -> MonthPlan | None:
    path = plan_path(year, month)
    if not path.exists():
        return None

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    constraints_by_id = {}
    for c_data in data.get("constraints", []):
        aid = c_data.get("assistant_id", "")
        constraints = AssistantConstraints(
            assistant_id=aid,
            unavailable_dates=[
                date.fromisoformat(d) for d in c_data.get("unavailable_dates", [])
            ],
            vacation_ranges=[
                (date.fromisoformat(start), date.fromisoformat(end))
                for start, end in c_data.get("vacation_ranges", [])
            ],
            max_consecutive_days=c_data.get("max_consecutive_days", 3),
            target_shifts=c_data.get("target_shifts"),
        )
        constraints_by_id[aid] = constraints

    loaded_assistants = []
    for assistant in assistants:
        updated_constraints = constraints_by_id.get(assistant.id, AssistantConstraints(assistant_id=assistant.id))
        updated_assistant = Assistant(
            id=assistant.id,
            name=assistant.name,
            color=assistant.color,
            constraints=updated_constraints,
            active=assistant.active,
        )
        loaded_assistants.append(updated_assistant)

    schedule = {}
    for day_str, entries_data in data.get("schedule", {}).items():
        day = int(day_str)
        entries = []
        for e_data in entries_data:
            entry = ShiftEntry(
                assistant_id=e_data.get("assistant_id", ""),
                shift_type=ShiftType(e_data.get("shift_type", "VOLL")),
                locked=e_data.get("locked", False),
            )
            entries.append(entry)
        schedule[day] = entries

    plan = MonthPlan(
        year=year,
        month=month,
        schedule=schedule,
        assistants=loaded_assistants,
        seed=data.get("seed"),
        created_at=data.get("created_at", ""),
        modified_at=data.get("modified_at", ""),
    )
    return plan
