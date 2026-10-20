"""Ablageordner "Formularantworten" fuer die Rueckmeldungen.

Liegt neben dem Programmordner (im Entwicklungsmodus im Projektstamm), damit
ihn kein Programm-Update anfasst. Je Monat ein Unterordner
("2026-11_November"); die Planerin legt dort die Antworten ab - als .txt
(Mailtext), .eml (gespeicherte Mail) oder .html. Beim Programmstart und
ueber "Datei > Ablageordner aktualisieren" werden neue oder geaenderte
Dateien ab dem heutigen Monat eingelesen. Was schon eingelesen wurde, steht
in eingelesen.json des Monatsordners (Dateiname, Groesse, Aenderungszeit) -
so ueberschreibt ein erneuter Start keine Handaenderungen; eine korrigierte
Rueckmeldung ist eine neue oder geaenderte Datei und wird uebernommen.
protokoll.txt im Monatsordner haelt fest, was wann eingelesen wurde (samt
Bemerkung des Helfers).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from models import MONTHS_DE
from persistence.atomic_io import read_json, write_json, DataFileError

INBOX_NAME = "Formularantworten"
# Beim Formular-Export und beim Aktualisieren werden Ordner fuer so viele
# Folgemonate angelegt
INBOX_MONTHS_AHEAD = 6
RECORD_FILE = "eingelesen.json"
PROTOCOL_FILE = "protokoll.txt"
README_FILE = "LIESMICH.txt"
ANSWER_SUFFIXES = (".txt", ".eml", ".html", ".htm")

README_TEXT = """Formularantworten - Rueckmeldungen der Helfer

Je Monat ein Ordner. Die Antwort eines Helfers hier ablegen:
- den Mailtext als Textdatei (.txt) speichern, oder
- die Mail selbst speichern (.eml), oder
- die vom Helfer geschickte Textdatei (.txt) aus dem Anhang.

Beim naechsten Programmstart (oder Datei > Ablageordner aktualisieren)
liest Johanna Assistenten alle neuen Dateien ab dem aktuellen Monat ein
und traegt Urlaub, Wunsch frei und Dienstwunsch der Helfer ein.
Eine korrigierte Rueckmeldung einfach als neue Datei dazulegen - sie
ersetzt die Eintraege des Helfers fuer diesen Monat.

eingelesen.json und protokoll.txt schreibt das Programm selbst.
"""


def _program_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def inbox_root() -> Path:
    if getattr(sys, "frozen", False):
        return _program_dir().parent / INBOX_NAME
    return _program_dir() / INBOX_NAME


def month_folder(year: int, month: int) -> Path:
    return inbox_root() / f"{year}-{month:02d}_{MONTHS_DE[month]}"


def _add_months(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def ensure_month_folders(year: int, month: int,
                         ahead: int = INBOX_MONTHS_AHEAD) -> list[Path]:
    """Ordner fuer den Monat und die naechsten `ahead` Monate anlegen
    (vorhandene bleiben unangetastet). Gibt die neu angelegten zurueck."""
    root = inbox_root()
    root.mkdir(parents=True, exist_ok=True)
    readme = root / README_FILE
    if not readme.exists():
        readme.write_text(README_TEXT, encoding="utf-8")
    created = []
    for delta in range(ahead + 1):
        folder = month_folder(*_add_months(year, month, delta))
        if not folder.exists():
            folder.mkdir(parents=True)
            created.append(folder)
    return created


def _folder_month(folder: Path) -> tuple[int, int] | None:
    head = folder.name[:7]
    if len(head) == 7 and head[4] == "-" and head[:4].isdigit() and head[5:].isdigit():
        return int(head[:4]), int(head[5:])
    return None


def _record_path(folder: Path) -> Path:
    return folder / RECORD_FILE


def _load_record(folder: Path) -> dict:
    try:
        data = read_json(_record_path(folder))
    except DataFileError:
        return {}
    return data if isinstance(data, dict) else {}


def _signature(path: Path) -> dict:
    stat = path.stat()
    return {"size": stat.st_size, "mtime": int(stat.st_mtime)}


def scan_new_files(min_month: tuple[int, int] | None = None) -> list[Path]:
    """Antwortdateien, die noch nicht (oder in anderer Fassung) eingelesen
    wurden - in allen Monatsordnern ab min_month ((Jahr, Monat), None =
    alle), chronologisch."""
    root = inbox_root()
    if not root.is_dir():
        return []
    result = []
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        ym = _folder_month(folder)
        if ym is None or (min_month is not None and ym < min_month):
            continue
        record = _load_record(folder)
        for path in sorted(folder.iterdir()):
            if not path.is_file() or path.suffix.lower() not in ANSWER_SUFFIXES:
                continue
            if path.name in (PROTOCOL_FILE, README_FILE) or path.name.startswith("rueckmeldung_"):
                continue  # Protokoll bzw. das Formular selbst
            if record.get(path.name) == _signature(path):
                continue
            result.append(path)
    return result


def mark_processed(path: Path, summary: str) -> None:
    folder = path.parent
    record = _load_record(folder)
    record[path.name] = _signature(path)
    write_json(_record_path(folder), record)
    append_protocol(folder, f"{path.name}: {summary}")


def append_protocol(folder: Path, line: str) -> None:
    stamp = datetime.now().strftime("%d.%m.%Y %H:%M")
    with open(folder / PROTOCOL_FILE, "a", encoding="utf-8") as f:
        f.write(f"{stamp}  {line}\n")
