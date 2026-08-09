"""Migration alter Dateiformate auf die aktuelle Version.

Regel (siehe BESCHREIBUNG.md): Wer ein Dateiformat aendert, erhoeht die
zugehoerige CURRENT_*_VERSION und ergaenzt hier einen Migrationsschritt.
Die Migrationen laufen schrittweise (v1 -> v2 -> ...), damit beliebig alte
Dateien nach einem Programm-Update weiter funktionieren.
"""
from __future__ import annotations

CURRENT_TEAM_VERSION = 3
CURRENT_PLAN_VERSION = 3
CURRENT_SETTINGS_VERSION = 3


def migrate_team(data) -> dict:
    """team.json: v1 war eine nackte Liste, ab v2 ein Objekt mit Versionsfeld."""
    if isinstance(data, list):
        data = {"version": 1, "assistants": data}

    version = data.get("version", 1)

    if version < 2:
        # v1 -> v2: nur Umhuellung in ein Objekt, Eintraege unveraendert
        version = 2

    if version < 3:
        # v2 -> v3: personenbezogene Constraints (Urlaube, Einzeltage,
        # Max. Folge, Min. Block) wandern monatsuebergreifend in team.json
        for assistant in data.get("assistants", []):
            assistant.setdefault("constraints", {
                "assistant_id": assistant.get("id", ""),
                "unavailable_dates": [],
                "vacation_ranges": [],
                "max_consecutive_days": 3,
                "min_block_days": 1,
            })
        version = 3

    data["version"] = CURRENT_TEAM_VERSION
    return data


def migrate_plan(data: dict) -> dict:
    version = data.get("version", 1)

    if version < 2:
        # v1 -> v2: ShiftEntry.generated und Constraints.min_block_days ergaenzen
        for entries in data.get("schedule", {}).values():
            for entry in entries:
                entry.setdefault("generated", False)
        for constraints in data.get("constraints", []):
            constraints.setdefault("min_block_days", 1)
        # Alt-Dateien der allerersten Version speicherten Assistenten samt
        # Constraints direkt im Plan
        for assistant in data.get("assistants", []):
            assistant.get("constraints", {}).setdefault("min_block_days", 1)
        version = 2

    if version < 3:
        # v2 -> v3: nur die (monatsbezogenen) Soll-Dienste bleiben im Plan
        # ("targets"); die uebrigen Constraints ziehen nach team.json um.
        # Die Alt-Constraints bleiben als legacy_constraints erhalten, damit
        # load_plan() sie einmalig in ein noch leeres Team uebernehmen kann.
        old_constraints = data.pop("constraints", [])
        data.setdefault("targets", {
            c.get("assistant_id", ""): c.get("target_shifts")
            for c in old_constraints
        })
        if old_constraints:
            data["legacy_constraints"] = old_constraints
        version = 3

    data["version"] = CURRENT_PLAN_VERSION
    return data


def migrate_settings(data: dict) -> dict:
    version = data.get("version", 1)

    if version < 2:
        # v1 -> v2: geteilte Kalenderansicht (zwei Monatshaelften untereinander)
        data.setdefault("split_view", False)
        version = 2

    if version < 3:
        # v2 -> v3: "Beim Ueberschreiben nachfragen" wird zu "Ueberschreiben
        # erlauben" - bewusst standardmaessig aus
        data.pop("confirm_overwrite", None)
        data.setdefault("allow_overwrite", False)
        version = 3

    data["version"] = CURRENT_SETTINGS_VERSION
    return data
