from __future__ import annotations
from dataclasses import dataclass, field
from .shift import ShiftEntry
from .assistant import Assistant


@dataclass
class MonthPlan:
    year: int
    month: int
    schedule: dict[int, list[ShiftEntry]] = field(default_factory=dict)
    assistants: list[Assistant] = field(default_factory=list)
    # Freitext-Notiz je Tag (Tag -> Text); leere Texte werden nicht gespeichert
    notes: dict[int, str] = field(default_factory=dict)
    seed: int | None = None
    created_at: str = ""
    modified_at: str = ""
