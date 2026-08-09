from __future__ import annotations
import json
from dataclasses import dataclass, asdict

from .json_store import DATA_DIR
from .migrations import migrate_settings, CURRENT_SETTINGS_VERSION

SETTINGS_FILE = DATA_DIR / "settings.json"


@dataclass
class AppSettings:
    # Zuletzt geoeffneter Monat - wird beim Start wiederhergestellt
    last_year: int | None = None
    last_month: int | None = None
    # Fenstergeometrie als Hex-String (QMainWindow.saveGeometry)
    window_geometry: str = ""
    # Beim Ueberschreiben von Eintraegen im Stempel-Modus nachfragen
    confirm_overwrite: bool = True
    seed: int = 42
    deterministic: bool = True
    # Geteilte Kalenderansicht: zweite Monatshaelfte unter der ersten
    split_view: bool = False


def load_settings() -> AppSettings:
    if not SETTINGS_FILE.exists():
        return AppSettings()

    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = migrate_settings(json.load(f))
    except (json.JSONDecodeError, OSError):
        return AppSettings()

    return AppSettings(
        last_year=data.get("last_year"),
        last_month=data.get("last_month"),
        window_geometry=data.get("window_geometry", ""),
        confirm_overwrite=data.get("confirm_overwrite", True),
        seed=data.get("seed", 42),
        deterministic=data.get("deterministic", True),
        split_view=data.get("split_view", False),
    )


def save_settings(settings: AppSettings) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data = {"version": CURRENT_SETTINGS_VERSION, **asdict(settings)}
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
