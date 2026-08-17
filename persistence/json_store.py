from __future__ import annotations
import sys
from datetime import date
from pathlib import Path

from models.plan import MonthPlan
from models.assistant import (
    Assistant, AssistantConstraints, absence_days, set_absence_days
)
from models.profile import AssistantSettings, SettingsProfile
from models.shift import ShiftEntry, ShiftType
from .migrations import (
    migrate_team,
    migrate_plan,
    CURRENT_TEAM_VERSION,
    CURRENT_PLAN_VERSION,
)
from .atomic_io import DataFileError, read_json, write_json


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
        "min_gap_days": c.min_gap_days,
        "oncall_attach": c.oncall_attach,
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
        min_gap_days=c_data.get("min_gap_days", 0),
        oncall_attach=c_data.get("oncall_attach", "none"),
        min_shifts=c_data.get("min_shifts"),
        max_shifts=c_data.get("max_shifts"),
    )


def _profile_settings_to_dict(s: AssistantSettings) -> dict:
    return {
        "min_shifts": s.min_shifts,
        "max_shifts": s.max_shifts,
        "max_consecutive_days": s.max_consecutive_days,
        "min_block_days": s.min_block_days,
        "min_gap_days": s.min_gap_days,
        "oncall_attach": s.oncall_attach,
    }


def _profile_settings_from_dict(d: dict) -> AssistantSettings:
    return AssistantSettings(
        min_shifts=d.get("min_shifts"),
        max_shifts=d.get("max_shifts"),
        max_consecutive_days=d.get("max_consecutive_days", 3),
        min_block_days=d.get("min_block_days", 1),
        min_gap_days=d.get("min_gap_days", 0),
        oncall_attach=d.get("oncall_attach", "none"),
    )


def _profile_to_dict(p: SettingsProfile) -> dict:
    return {
        "name": p.name,
        "settings": {
            aid: _profile_settings_to_dict(s) for aid, s in p.settings.items()
        },
    }


def _profile_from_dict(d: dict, fallback_name: str) -> SettingsProfile:
    return SettingsProfile(
        name=d.get("name", fallback_name),
        settings={
            aid: _profile_settings_from_dict(s_data)
            for aid, s_data in d.get("settings", {}).items()
        },
    )


def default_profiles() -> list[SettingsProfile]:
    return [SettingsProfile(name="Vorlage 1"), SettingsProfile(name="Vorlage 2")]


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
    write_json(path, data)


def load(path: str | Path) -> MonthPlan:
    path = Path(path)
    raw = read_json(path)
    if raw is None:
        raise DataFileError(path, "Datei nicht gefunden")
    data = migrate_plan(raw)

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


def save_team(assistants: list[Assistant],
              profiles: list[SettingsProfile] | None = None) -> None:
    # Personenbezogene Constraints (Urlaube, Einzeltage, Max/Min) leben
    # monatsuebergreifend hier; nur die Soll-Dienste (min/max) gehoeren
    # zum Monatsplan. Die zwei Einstellungs-Vorlagen (Team-Tab) liegen
    # ebenfalls hier
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if profiles is None:
        profiles = load_profiles()
    data = {
        "version": CURRENT_TEAM_VERSION,
        "assistants": [
            {
                **_assistant_to_dict(a, with_constraints=False),
                "constraints": _constraints_to_dict(a.constraints, include_target=False),
            }
            for a in assistants
        ],
        "profiles": [_profile_to_dict(p) for p in profiles],
    }
    write_json(TEAM_FILE, data)


def load_team() -> list[Assistant]:
    raw = read_json(TEAM_FILE)
    if raw is None:
        return []
    data = migrate_team(raw)

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


def load_profiles() -> list[SettingsProfile]:
    """Laedt die zwei Einstellungs-Vorlagen aus team.json (immer genau
    zwei; fehlende werden mit leeren Vorlagen aufgefuellt)."""
    profiles = default_profiles()
    raw = read_json(TEAM_FILE)
    if raw is None:
        return profiles
    data = migrate_team(raw)

    for i, p_data in enumerate(data.get("profiles", [])[:2]):
        if isinstance(p_data, dict):
            profiles[i] = _profile_from_dict(p_data, profiles[i].name)
    return profiles


# --- Monatsplaene (automatische Ablage unter data/plans/) ---

def plan_path(year: int, month: int) -> Path:
    return PLANS_DIR / f"plan_{year}_{month:02d}.json"


def save_plan(plan: MonthPlan) -> None:
    data = {
        "version": CURRENT_PLAN_VERSION,
        "year": plan.year,
        "month": plan.month,
        "schedule": _schedule_to_dict(plan.schedule),
        # Schnappschuss der Planungs-Einstellungen dieses Monats (z. B. aus
        # einer Vorlage uebernommen); Abwesenheiten liegen weiter in team.json
        "settings": {
            a.id: {
                "min": a.constraints.min_shifts,
                "max": a.constraints.max_shifts,
                "max_consecutive_days": a.constraints.max_consecutive_days,
                "min_block_days": a.constraints.min_block_days,
                "min_gap_days": a.constraints.min_gap_days,
                "oncall_attach": a.constraints.oncall_attach,
            }
            for a in plan.assistants
        },
        "seed": plan.seed,
        "created_at": plan.created_at,
        "modified_at": plan.modified_at,
    }
    write_json(plan_path(plan.year, plan.month), data)


def load_plan(year: int, month: int, assistants: list[Assistant]) -> MonthPlan | None:
    """Laedt den Monatsplan. Die uebergebenen Assistenten (aus team.json)
    behalten ihre Abwesenheiten; die Planungs-Einstellungen (Soll-Spanne,
    Max. Folge, Min. Block, Mindestabstand, RB-Anhang) kommen aus dem
    Schnappschuss der Monatsdatei. Alte Dateien kennen nur die Soll-Spanne -
    die uebrigen Felder behalten dann die Werte aus team.json."""
    raw = read_json(plan_path(year, month))
    if raw is None:
        return None
    data = migrate_plan(raw)

    settings_map = data.get("settings", {})

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
        s = settings_map.get(assistant.id)
        c = assistant.constraints
        if isinstance(s, dict):
            c.min_shifts = s.get("min")
            c.max_shifts = s.get("max")
            # Nur vorhandene Felder uebernehmen: aus v4 migrierte Dateien
            # kennen nur die Soll-Spanne, der Rest bleibt aus team.json
            if "max_consecutive_days" in s:
                c.max_consecutive_days = s["max_consecutive_days"]
            if "min_block_days" in s:
                c.min_block_days = s["min_block_days"]
            if "min_gap_days" in s:
                c.min_gap_days = s["min_gap_days"]
            if "oncall_attach" in s:
                c.oncall_attach = s["oncall_attach"]
        else:
            # Helfer ohne Eintrag (z. B. spaeter angelegt): Soll auf Auto
            c.min_shifts = None
            c.max_shifts = None

    return MonthPlan(
        year=year,
        month=month,
        schedule=_schedule_from_dict(data.get("schedule", {})),
        assistants=assistants,
        seed=data.get("seed"),
        created_at=data.get("created_at", ""),
        modified_at=data.get("modified_at", ""),
    )
