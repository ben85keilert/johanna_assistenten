"""Menue "Hilfe": Bedienungsanleitung, Planungslogik, Info/Version.

Die Hilfe liegt als HTML im Ordner hilfe/ (mit Screenshots in hilfe/bilder/)
und oeffnet sich im Browser - so laesst sie sich auch ausdrucken oder
weitergeben. Suchreihenfolge wie bei den Vorlagen: "hilfe" neben dem
Programm, dann die mitgelieferte im Build (PyInstaller --add-data), dann
die im Projekt. Die Screenshots erzeugt tools/make_screenshots.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox

from version import __version__, GITHUB_REPO

HELP_FILES = {
    "bedienung": "bedienung.html",
    "planungslogik": "planungslogik.html",
}


def help_candidates(name: str) -> list[Path]:
    filename = HELP_FILES[name]
    project_root = Path(__file__).resolve().parent.parent
    candidates = []
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).parent / "hilfe" / filename)
        bundled = getattr(sys, "_MEIPASS", None)
        if bundled:
            candidates.append(Path(bundled) / "hilfe" / filename)
    candidates.append(project_root / "hilfe" / filename)
    return candidates


def help_path(name: str) -> Path | None:
    for candidate in help_candidates(name):
        if candidate.is_file():
            return candidate
    return None


def open_help(parent, name: str) -> None:
    path = help_path(name)
    if path is None:
        QMessageBox.warning(
            parent, "Hilfe",
            "Die Hilfedatei wurde nicht gefunden. Gesucht:\n"
            + "\n".join(str(c) for c in help_candidates(name)),
        )
        return
    if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
        QMessageBox.information(
            parent, "Hilfe",
            f"Die Hilfe liegt hier und laesst sich im Browser oeffnen:\n{path}",
        )


def show_about(parent, data_dir: Path, inbox_dir: Path) -> None:
    repo_url = f"https://github.com/{GITHUB_REPO}"
    QMessageBox.about(
        parent, "Info / Version",
        f"<h3>Johanna Assistenten</h3>"
        f"<p>Version <b>{__version__}</b></p>"
        f"<p>Dienstplanung fuer das Assistenz-Team: faire Verteilung der "
        f"Tage eines Monats unter Beachtung von Urlaub, Wuenschen und "
        f"Regeln je Helfer.</p>"
        f"<p>Quellcode, Versionen und Fehlermeldungen:<br>"
        f"<a href=\"{repo_url}\">{repo_url}</a><br>"
        f"Neue Versionen: <a href=\"{repo_url}/releases\">{repo_url}/releases</a></p>"
        f"<p>Daten: <code>{data_dir}</code><br>"
        f"Rueckmeldungen: <code>{inbox_dir}</code></p>"
        f"<p>Hilfe: Menue <i>Hilfe &rarr; Bedienung</i> und "
        f"<i>Hilfe &rarr; Planungslogik</i>.</p>",
    )
