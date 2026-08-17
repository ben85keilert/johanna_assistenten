"""Robustes Lesen und Schreiben der JSON-Dateien.

Grundregel: Ein Absturz, ein Stromausfall oder ein abgewuergter Prozess
waehrend des Speicherns darf niemals den zuletzt gueltigen Stand vernichten.
Direktes ``open(path, "w")`` wuerde die Zieldatei sofort leeren und erst
danach neu befuellen - stirbt das Programm dazwischen, ist auch die alte
Fassung weg. Deshalb schreibt ``write_json``:

1. in eine ``.tmp``-Datei im selben Ordner (mit ``fsync`` auf die Platte),
2. legt eine Sicherheitskopie der bisherigen Datei als ``.bak`` an,
3. verschiebt die ``.tmp``-Datei per ``os.replace`` atomar ans Ziel.

Zu jedem Zeitpunkt existiert also mindestens eine vollstaendige Fassung.
``read_json`` greift bei einer beschaedigten Datei automatisch auf die
``.bak``-Kopie zurueck und meldet das ueber ``pop_recoveries()`` ans UI.
"""
from __future__ import annotations
import json
import os
import shutil
from pathlib import Path


class DataFileError(Exception):
    """Datei ist vorhanden, aber unlesbar - auch die Sicherungskopie.

    Wird bewusst geworfen statt leere Daten zurueckzugeben: mit einem leeren
    Team weiterzuarbeiten wuerde die beschaedigte Datei beim naechsten
    Speichern endgueltig ueberschreiben.
    """

    def __init__(self, path: str | Path, reason: str):
        self.path = Path(path)
        self.reason = reason
        super().__init__(f"{self.path}: {reason}")


# Dateien, die aus ihrer .bak-Kopie gerettet werden mussten. Das UI holt die
# Liste nach dem Start ab und weist den Nutzer darauf hin.
_recoveries: list[str] = []


def pop_recoveries() -> list[str]:
    """Gibt die Hinweise zu wiederhergestellten Dateien zurueck und leert sie."""
    global _recoveries
    notes, _recoveries = _recoveries, []
    return notes


def backup_path(path: str | Path) -> Path:
    path = Path(path)
    return path.with_name(path.name + ".bak")


def _tmp_path(path: Path) -> Path:
    return path.with_name(path.name + ".tmp")


def _fsync_dir(folder: Path) -> None:
    # Erst ein fsync auf das Verzeichnis macht das Umbenennen wirklich
    # dauerhaft. Unter Windows laesst sich ein Verzeichnis nicht oeffnen -
    # dort ist os.replace ohnehin atomar, der Schritt entfaellt einfach.
    try:
        fd = os.open(folder, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def write_json(path: str | Path, data) -> None:
    """Schreibt ``data`` als JSON - atomar und mit .bak-Sicherung."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = _tmp_path(path)

    # Erst serialisieren, dann schreiben: ein Fehler in den Daten darf die
    # Zieldatei gar nicht erst anfassen
    text = json.dumps(data, indent=2, ensure_ascii=False)

    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())

    if path.exists():
        # Kopieren statt Umbenennen: die gueltige Datei bleibt bis zum
        # abschliessenden os.replace unangetastet
        try:
            shutil.copy2(path, backup_path(path))
        except OSError:
            # Kein Backup moeglich (z. B. Platte voll) - das Speichern selbst
            # ist wichtiger und laeuft trotzdem atomar weiter
            pass

    os.replace(tmp, path)
    _fsync_dir(path.parent)


def read_json(path: str | Path) -> dict | list | None:
    """Liest die JSON-Datei.

    ``None`` = Datei existiert (noch) nicht. Ist der Inhalt beschaedigt, wird
    automatisch die ``.bak``-Kopie verwendet; sind beide unlesbar, folgt ein
    ``DataFileError``.
    """
    path = Path(path)
    if not path.exists():
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as primary_error:
        backup = backup_path(path)
        if backup.exists():
            try:
                with open(backup, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError, UnicodeDecodeError):
                raise DataFileError(
                    path,
                    f"Datei und Sicherungskopie sind beschaedigt ({primary_error})",
                ) from primary_error
            _recoveries.append(
                f"{path.name} war beschaedigt und wurde aus der "
                f"Sicherungskopie {backup.name} wiederhergestellt."
            )
            return data
        raise DataFileError(path, f"Datei ist beschaedigt ({primary_error})") from primary_error
