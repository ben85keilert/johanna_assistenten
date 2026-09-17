"""Migration alter Dateiformate auf die aktuelle Version.

Regel (siehe BESCHREIBUNG.md): Wer ein Dateiformat aendert, erhoeht die
zugehoerige CURRENT_*_VERSION und ergaenzt hier einen Migrationsschritt.
Die Migrationen laufen schrittweise (v1 -> v2 -> ...), damit beliebig alte
Dateien nach einem Programm-Update weiter funktionieren.
"""
from __future__ import annotations
import copy

CURRENT_TEAM_VERSION = 6
CURRENT_PLAN_VERSION = 7
CURRENT_SETTINGS_VERSION = 5

# Einheitliche Farben je Eintragsart (statt einer Farbe je Helfer).
# Aenderbar unter Einstellungen > Farben; hier die Standardwerte.
DEFAULT_ENTRY_COLORS = {
    "FULL": "#5B9BD5",            # Tagesdienst: Blau
    "HALF_MORNING": "#4DB6AC",    # VM: Tuerkis
    "HALF_AFTERNOON": "#F2A54A",  # NM: Orange
    "ON_CALL": "#9575CD",         # Rufbereitschaft: Violett
    "VACATION": "#81C784",        # Urlaub: Gruen
    "BLOCK": "#E57373",           # Block: Rot
}


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

    if version < 4:
        # v3 -> v4: Block-Zeiten (zweite Abwesenheitsart neben Urlaub)
        for assistant in data.get("assistants", []):
            constraints = assistant.get("constraints", {})
            constraints.setdefault("blocked_dates", [])
            constraints.setdefault("blocked_ranges", [])
        version = 4

    if version < 5:
        # v4 -> v5: Mindestabstand + RB-Anhang je Helfer; ausserdem zwei
        # Einstellungs-Vorlagen, anfangs beide aus den bestehenden Werten
        for assistant in data.get("assistants", []):
            constraints = assistant.get("constraints", {})
            constraints.setdefault("min_gap_days", 0)
            constraints.setdefault("oncall_attach", "none")
        if not data.get("profiles"):
            settings = {}
            for assistant in data.get("assistants", []):
                constraints = assistant.get("constraints", {})
                settings[assistant.get("id", "")] = {
                    "min_shifts": None,
                    "max_shifts": None,
                    "max_consecutive_days": constraints.get("max_consecutive_days", 3),
                    "min_block_days": constraints.get("min_block_days", 1),
                    "min_gap_days": constraints.get("min_gap_days", 0),
                    "oncall_attach": constraints.get("oncall_attach", "none"),
                }
            data["profiles"] = [
                {"name": "Vorlage 1", "settings": settings},
                {"name": "Vorlage 2", "settings": copy.deepcopy(settings)},
            ]
        version = 5

    if version < 6:
        # v5 -> v6: Freiwunsch-Kontingent je Helfer (None = "Alle": alle
        # Block-Tage bleiben hart wie bisher) - auch in beiden Vorlagen
        for assistant in data.get("assistants", []):
            assistant.get("constraints", {}).setdefault("free_wish_quota", None)
        for profile in data.get("profiles", []):
            for settings in profile.get("settings", {}).values():
                if isinstance(settings, dict):
                    settings.setdefault("free_wish_quota", None)
        version = 6

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

    if version < 4:
        # v3 -> v4: Soll-Dienste werden eine Min/Max-Spanne; ein alter fester
        # Wert wird zu min == max, "Auto" (null) zu beiden null
        data["targets"] = {
            aid: {"min": t, "max": t} if not isinstance(t, dict) else t
            for aid, t in data.get("targets", {}).items()
        }
        # Vollplan-Dateien (Datei > Speichern) tragen Constraints samt Ziel
        # direkt bei den Assistenten
        for assistant in data.get("assistants", []):
            constraints = assistant.get("constraints", {})
            if "target_shifts" in constraints:
                t = constraints.pop("target_shifts")
                constraints.setdefault("min_shifts", t)
                constraints.setdefault("max_shifts", t)
            constraints.setdefault("blocked_dates", [])
            constraints.setdefault("blocked_ranges", [])
        version = 4

    if version < 5:
        # v4 -> v5: der Monat speichert die uebernommenen Einstellungen
        # vollstaendig ("settings" statt nur "targets"). Alte Dateien kennen
        # nur die Soll-Spanne; die uebrigen Felder fehlen dann und kommen
        # beim Laden weiter aus team.json
        targets = data.pop("targets", {})
        data.setdefault("settings", {
            aid: (
                {"min": t.get("min"), "max": t.get("max")}
                if isinstance(t, dict) else {"min": t, "max": t}
            )
            for aid, t in targets.items()
        })
        # Vollplan-Dateien (Datei > Speichern): neue Constraint-Felder
        for assistant in data.get("assistants", []):
            constraints = assistant.get("constraints", {})
            constraints.setdefault("min_gap_days", 0)
            constraints.setdefault("oncall_attach", "none")
        version = 5

    if version < 6:
        # v5 -> v6: Freitext-Notizen je Tag ("notes": Tag -> Text)
        data.setdefault("notes", {})
        version = 6

    if version < 7:
        # v6 -> v7: Kandidaten-Mechanik (candidate/chosen je Eintrag) und
        # Freiwunsch-Kontingent; Vollplan-Dateien tragen Constraints direkt
        for entries in data.get("schedule", {}).values():
            for entry in entries:
                entry.setdefault("candidate", False)
                entry.setdefault("chosen", False)
        for assistant in data.get("assistants", []):
            assistant.get("constraints", {}).setdefault("free_wish_quota", None)
        version = 7

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

    if version < 4:
        # v3 -> v4: einstellbare Farben je Eintragsart (Farbmanagement)
        data.setdefault("entry_colors", dict(DEFAULT_ENTRY_COLORS))
        version = 4

    if version < 5:
        # v4 -> v5: automatische Update-Pruefung - uebersprungene Version merken
        data.setdefault("skipped_version", "")
        version = 5

    data["version"] = CURRENT_SETTINGS_VERSION
    return data
