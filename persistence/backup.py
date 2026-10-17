"""Datensicherung: Kopien des data-Ordners (Team, Plaene, Einstellungen).

Programm und Daten sind getrennt: der Programmordner (exe + _internal) darf
jederzeit durch eine neue Version ueberschrieben werden, data\\ bleibt
liegen (das Release-ZIP enthaelt keinen data-Ordner, der Auto-Updater
spart ihn aus). Zusaetzlich sichert das Programm die Daten selbst:

- Automatisch beim ersten Start einer neuen Programmversion - bevor diese
  Dateien migriert und im neuen Format speichert - nach
  data/sicherungen/<Zeitstempel>_v<alt>_vor_v<neu>/. Es bleiben die
  letzten KEEP_AUTO_BACKUPS Sicherungen.
- Von Hand ueber Datei > Datensicherung erstellen...: ein ZIP an beliebiger
  Stelle (z. B. USB-Stick).

Zurueckholen: Programm schliessen, die Dateien aus der Sicherung (bzw. aus
dem ZIP-Ordner data) zurueck nach data\\ kopieren.
"""
from __future__ import annotations

import shutil
import zipfile
from datetime import datetime
from pathlib import Path

from .json_store import DATA_DIR

BACKUP_DIR = DATA_DIR / "sicherungen"
KEEP_AUTO_BACKUPS = 10


def _data_files() -> list[Path]:
    """Alle Datendateien (team.json, settings.json, plans/*.json) ohne
    Zwischen-/Sicherungsdateien und ohne die Sicherungen selbst."""
    if not DATA_DIR.is_dir():
        return []
    return sorted(
        f for f in DATA_DIR.rglob("*.json")
        if f.is_file() and BACKUP_DIR not in f.parents
    )


def _stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H%M%S")


def backup_before_version_change(old_version: str, new_version: str) -> Path | None:
    """Kopie aller Datendateien vor dem ersten Speichern einer neuen
    Programmversion. None, wenn es (noch) keine Daten gibt."""
    files = _data_files()
    if not files:
        return None
    old = f"v{old_version}" if old_version else "v-alt"
    target = BACKUP_DIR / f"{_stamp()}_{old}_vor_v{new_version}"
    for f in files:
        dest = target / f.relative_to(DATA_DIR)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dest)
    _prune_auto_backups()
    return target


def _prune_auto_backups():
    backups = sorted(p for p in BACKUP_DIR.iterdir() if p.is_dir())
    for old in backups[:-KEEP_AUTO_BACKUPS]:
        shutil.rmtree(old, ignore_errors=True)


def create_backup_zip(folder: str | Path) -> str:
    """Datensicherung von Hand: ZIP mit dem Ordner data (ohne die
    automatischen Sicherungen) im gewaehlten Ordner."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    zip_path = folder / f"JohannaAssistenten-Daten_{_stamp()}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for f in _data_files():
            archive.write(f, Path("data") / f.relative_to(DATA_DIR))
    return str(zip_path)
