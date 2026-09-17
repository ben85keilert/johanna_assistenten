"""Automatisches Update ueber GitHub-Releases (portable Windows-Version).

Ablauf: Beim Start (bzw. ueber Einstellungen > "Nach Updates suchen...")
wird das neueste Release von GitHub geholt und mit der laufenden Version
verglichen. Bestaetigt der Nutzer, laedt ein Hintergrund-Thread das
Release-ZIP nach %TEMP%, entpackt und validiert es. Erst dann startet ein
kleines Batch-Skript, das auf das Programmende wartet, den Programmordner
per robocopy spiegelt (der Ordner "data" bleibt dabei unangetastet) und
die neue Version startet. Der PyInstaller-Build ist ein Ordner (exe +
_internal), deshalb der Tausch nach Programmende - eine laufende exe und
ihre DLLs lassen sich unter Windows nicht ueberschreiben.

Die Pruefung schlaegt niemals laut fehl: jeder Fehler (kein Release,
Rate-Limit, keine Internetverbindung) liefert None, damit der
Programmstart nicht gestoert wird.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from version import GITHUB_REPO

# Namen aus dem Build-Workflow (build-windows.yml) - Teil des
# Update-Vertrags, duerfen dort nicht umbenannt werden
ASSET_NAME = "JohannaAssistenten-windows.zip"
DIST_DIR_NAME = "JohannaAssistenten"
EXE_NAME = "JohannaAssistenten.exe"

_USER_AGENT = "JohannaAssistenten"


class UpdateCancelled(Exception):
    """Der Nutzer hat den Download abgebrochen."""


# --- Versionsvergleich --------------------------------------------------

def parse_version(text) -> tuple[int, ...] | None:
    """"v1.2.3" / "1.0" -> (1, 2, 3) / (1, 0); Unlesbares -> None."""
    if not isinstance(text, str):
        return None
    text = text.strip().lstrip("vV")
    if not text:
        return None
    parts = []
    for part in text.split("."):
        match = re.match(r"\d+", part)
        if not match:
            return None
        parts.append(int(match.group()))
    return tuple(parts)


def is_newer(remote_tag, local_version) -> bool:
    """True, wenn der Release-Tag neuer ist als die laufende Version.

    Unlesbare Versionen ergeben False - im Zweifel kein Update anbieten."""
    remote = parse_version(remote_tag)
    local = parse_version(local_version)
    if remote is None or local is None:
        return False
    length = max(len(remote), len(local))
    remote += (0,) * (length - len(remote))
    local += (0,) * (length - len(local))
    return remote > local


# --- GitHub-Abfrage und Download ----------------------------------------

def fetch_latest_release(timeout: float = 10) -> dict | None:
    """Neuestes Release mit Windows-ZIP, oder None bei jedem Fehler.

    404 = noch kein Release, 403 = Rate-Limit, dazu Netzfehler und kaputtes
    JSON - alles fuehrt still zu None, der Start soll nie gestoert werden."""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    request = urllib.request.Request(url, headers={
        "User-Agent": _USER_AGENT,
        "Accept": "application/vnd.github+json",
    })
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.load(response)
        tag = data.get("tag_name") or ""
        asset = next(
            (a for a in data.get("assets", []) if a.get("name") == ASSET_NAME),
            None,
        )
        if not tag or asset is None or not asset.get("browser_download_url"):
            return None
        return {
            "tag": tag,
            "zip_url": asset["browser_download_url"],
            "notes": data.get("body") or "",
        }
    except Exception:
        return None


def download_and_extract(zip_url: str, progress_cb=None,
                         cancelled=None) -> Path:
    """Laedt das Release-ZIP nach %TEMP%, entpackt und validiert es.

    Liefert den entpackten Programmordner. Erst nach vollstaendigem,
    validiertem Entpacken passiert etwas am installierten Programm."""
    tmp = Path(tempfile.mkdtemp(prefix="johanna_update_"))
    zip_path = tmp / ASSET_NAME
    request = urllib.request.Request(
        zip_url, headers={"User-Agent": _USER_AGENT}
    )
    with urllib.request.urlopen(request, timeout=30) as response, \
            open(zip_path, "wb") as out:
        total = int(response.headers.get("Content-Length") or 0)
        received = 0
        while True:
            if cancelled is not None and cancelled():
                raise UpdateCancelled()
            chunk = response.read(65536)
            if not chunk:
                break
            out.write(chunk)
            received += len(chunk)
            if progress_cb is not None:
                progress_cb(received, total)

    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(tmp)
    new_dir = tmp / DIST_DIR_NAME
    if not (new_dir / EXE_NAME).is_file():
        raise RuntimeError(
            f"Das heruntergeladene Update ist unvollstaendig ({EXE_NAME} fehlt)."
        )
    return new_dir


# --- Ordnertausch nach Programmende -------------------------------------

def build_swap_script(new_dir: Path, app_dir: Path, pid: int) -> str:
    """Batch-Skript: auf Prozessende warten, Ordner spiegeln, neu starten.

    robocopy /MIR spiegelt den neuen Build in den Programmordner; /XD
    nimmt den "data"-Ordner davon aus, er bleibt unangetastet (siehe
    README: Daten liegen neben der exe und ueberleben jedes Update).
    Exit-Codes < 8 sind bei robocopy Erfolg. Nur ASCII verwenden."""
    return f"""@echo off
rem Automatisches Update Johanna Assistenten
set tries=0
:wait
set /a tries+=1
if %tries% gtr 120 goto copy
tasklist /FI "PID eq {pid}" | find "{pid}" >nul
if not errorlevel 1 (
    ping -n 2 127.0.0.1 >nul
    goto wait
)
:copy
robocopy "{new_dir}" "{app_dir}" /MIR /XD "{app_dir}\\data" "{new_dir}\\data" /R:5 /W:2 >nul
if errorlevel 8 (
    echo Update fehlgeschlagen - bitte das ZIP von GitHub manuell entpacken.
    pause
    exit /b 1
)
start "" "{app_dir}\\{EXE_NAME}"
rd /s /q "{new_dir}"
del "%~f0"
"""


def launch_swap_and_restart(new_dir: Path, app_dir: Path) -> None:
    """Startet das Tausch-Skript; der Aufrufer beendet danach das Programm."""
    script = build_swap_script(new_dir, app_dir, os.getpid())
    bat_path = Path(tempfile.gettempdir()) / "johanna_update.bat"
    bat_path.write_text(script, encoding="ascii")
    subprocess.Popen(
        ["cmd.exe", "/c", str(bat_path)],
        creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
        close_fds=True,
        cwd=tempfile.gettempdir(),
    )


# --- Qt-Threads (UI bleibt fluessig) ------------------------------------

class UpdateChecker(QThread):
    """Fragt das neueste Release im Hintergrund ab."""

    # dict mit tag/zip_url/notes oder None
    result = Signal(object)

    def run(self):
        self.result.emit(fetch_latest_release())


class UpdateDownloader(QThread):
    """Laedt und entpackt das Update im Hintergrund."""

    progress = Signal(int, int)      # empfangen, gesamt (0 = unbekannt)
    finished_ok = Signal(object)     # Path des entpackten Programmordners
    failed = Signal(str)

    def __init__(self, zip_url: str, parent=None):
        super().__init__(parent)
        self._zip_url = zip_url
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            new_dir = download_and_extract(
                self._zip_url,
                progress_cb=self.progress.emit,
                cancelled=lambda: self._cancelled,
            )
        except UpdateCancelled:
            return
        except Exception as e:
            self.failed.emit(str(e))
        else:
            self.finished_ok.emit(new_dir)
