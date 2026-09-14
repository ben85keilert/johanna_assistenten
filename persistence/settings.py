from __future__ import annotations
from dataclasses import dataclass, asdict, field

from .json_store import DATA_DIR
from .atomic_io import DataFileError, read_json, write_json
from .migrations import (
    migrate_settings, CURRENT_SETTINGS_VERSION, DEFAULT_ENTRY_COLORS,
)

SETTINGS_FILE = DATA_DIR / "settings.json"


@dataclass
class AppSettings:
    # Zuletzt geoeffneter Monat - wird beim Start wiederhergestellt
    last_year: int | None = None
    last_month: int | None = None
    # Fenstergeometrie als Hex-String (QMainWindow.saveGeometry)
    window_geometry: str = ""
    # Stempel duerfen vorhandene Eintraege anderen Typs ueberschreiben
    # (bewusst standardmaessig aus)
    allow_overwrite: bool = False
    seed: int = 42
    deterministic: bool = True
    # Geteilte Kalenderansicht: zweite Monatshaelfte unter der ersten
    split_view: bool = False
    # Farbe je Eintragsart (FULL/HALF_MORNING/HALF_AFTERNOON/ON_CALL/
    # VACATION/BLOCK) als Hex-String; einstellbar unter Einstellungen > Farben
    entry_colors: dict[str, str] = field(
        default_factory=lambda: dict(DEFAULT_ENTRY_COLORS)
    )


def load_settings() -> AppSettings:
    # Anders als Team und Plan enthaelt diese Datei keine Nutzerdaten, nur
    # Sitzungszustand - ist sie unrettbar kaputt, wird mit Defaults gestartet
    try:
        raw = read_json(SETTINGS_FILE)
    except DataFileError:
        raw = None
    if raw is None:
        return AppSettings()
    data = migrate_settings(raw)

    return AppSettings(
        last_year=data.get("last_year"),
        last_month=data.get("last_month"),
        window_geometry=data.get("window_geometry", ""),
        allow_overwrite=data.get("allow_overwrite", False),
        seed=data.get("seed", 42),
        deterministic=data.get("deterministic", True),
        split_view=data.get("split_view", False),
        # Fehlende Arten (z. B. nach Updates) mit Standardfarben auffuellen
        entry_colors={
            **DEFAULT_ENTRY_COLORS,
            **{
                k: v for k, v in data.get("entry_colors", {}).items()
                if isinstance(v, str)
            },
        },
    )


def save_settings(settings: AppSettings) -> None:
    data = {"version": CURRENT_SETTINGS_VERSION, **asdict(settings)}
    write_json(SETTINGS_FILE, data)
