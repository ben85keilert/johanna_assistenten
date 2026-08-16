"""Einstellungs-Vorlagen fuer das Team.

Eine Vorlage buendelt die Planungs-Einstellungen aller Helfer (Soll-Dienste,
Max. Folge, Min. Block, Mindestabstand, RB-Anhang). Im Team-Tab gibt es zwei
Vorlagen, die man getrennt pflegen und per Button in den Dienstplan des
aktuellen Monats uebernehmen kann. Abwesenheiten (Urlaub/Block) gehoeren
nicht zur Vorlage - sie sind datumsbasiert und gelten immer.
"""
from __future__ import annotations
from dataclasses import dataclass, field

from .assistant import AssistantConstraints


@dataclass
class AssistantSettings:
    """Planungs-Einstellungen eines Helfers innerhalb einer Vorlage."""
    min_shifts: int | None = None
    max_shifts: int | None = None
    max_consecutive_days: int = 3
    min_block_days: int = 1
    min_gap_days: int = 0
    oncall_attach: str = "none"


@dataclass
class SettingsProfile:
    name: str
    # assistant_id -> Einstellungen
    settings: dict[str, AssistantSettings] = field(default_factory=dict)


def settings_from_constraints(c: AssistantConstraints) -> AssistantSettings:
    return AssistantSettings(
        min_shifts=c.min_shifts,
        max_shifts=c.max_shifts,
        max_consecutive_days=c.max_consecutive_days,
        min_block_days=c.min_block_days,
        min_gap_days=c.min_gap_days,
        oncall_attach=c.oncall_attach,
    )


def apply_settings(c: AssistantConstraints, s: AssistantSettings) -> None:
    """Uebertraegt eine Vorlagen-Einstellung in die Constraints eines
    Helfers (Abwesenheiten bleiben unberuehrt)."""
    c.min_shifts = s.min_shifts
    c.max_shifts = s.max_shifts
    c.max_consecutive_days = s.max_consecutive_days
    c.min_block_days = s.min_block_days
    c.min_gap_days = s.min_gap_days
    c.oncall_attach = s.oncall_attach
