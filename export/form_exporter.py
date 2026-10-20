"""Rueckmeldeformular (HTML) fuer die Helfer erzeugen.

Die Vorlage vorlagen/rueckmeldung.html ist ein eigenstaendiges Formular
(laeuft offline in jedem Browser, auch am Handy): Helfer waehlen ihren
Namen, tippen Urlaub / Wunsch frei / Dienstwunsch im Kalender an und
schicken den fertigen Mailtext ab. Die letzte Zeile des Texts ist die
Maschinenzeile, z. B.

    JA1;2026-11;8cdf0de4;T:2026-10-20T14:03:05;U:3,10-14;W:5,6;D:7-9;N:<Bemerkung>;END

(Format, Monat, Helfer-ID, Zeitstempel, Urlaub, Wunsch, Dienstwunsch als
Tageslisten mit Bereichen, Bemerkung URL-kodiert, Ende-Zeichen) - sie laesst sich ohne KI eindeutig
einlesen (feedback/parser.py), auch umgebrochen oder zitiert.

Beim Erzeugen setzt das Programm zwischen die Marker /*CONFIG*/ den
Empfaenger, die Helfer des geoeffneten Monats und den Monat selbst ein
(dann ist der Monat im Formular fest). Die Datei wird von Hand verschickt
(z. B. als Anhang im Webmailer) - eine Mailprogramm-Anbindung gibt es
bewusst nicht.

Vorlage suchen: zuerst "vorlagen" neben dem Programm (von Hand angepasste
Fassung), dann die mitgelieferte im Build (PyInstaller --add-data), sonst
die im Projekt.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from models import MonthPlan

TEMPLATE_NAME = "rueckmeldung.html"
_MARKER = re.compile(r"/\*CONFIG\*/.*?/\*CONFIG\*/", re.S)


def template_candidates() -> list[Path]:
    project_root = Path(__file__).resolve().parent.parent
    candidates = []
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).parent / "vorlagen" / TEMPLATE_NAME)
        bundled = getattr(sys, "_MEIPASS", None)
        if bundled:
            candidates.append(Path(bundled) / "vorlagen" / TEMPLATE_NAME)
    candidates.append(project_root / "vorlagen" / TEMPLATE_NAME)
    return candidates


def template_path() -> Path:
    for candidate in template_candidates():
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        "Vorlage vorlagen/" + TEMPLATE_NAME + " nicht gefunden (gesucht: "
        + ", ".join(str(c) for c in template_candidates()) + ")"
    )


def render_form(plan: MonthPlan, recipient: str = "") -> str:
    """Formular-HTML fuer den Monat des Plans mit seinen aktiven Helfern."""
    config = {
        "empfaenger": recipient.strip(),
        "team": [[a.id, a.name] for a in plan.assistants if a.active],
        "jahr": plan.year,
        "monat": plan.month,
    }
    template = template_path().read_text(encoding="utf-8")
    replacement = "/*CONFIG*/" + json.dumps(config, ensure_ascii=False) + "/*CONFIG*/"
    html, count = _MARKER.subn(lambda _m: replacement, template, count=1)
    if count != 1:
        raise ValueError("Vorlage ohne /*CONFIG*/-Marker: " + str(template_path()))
    return html


def export_form(plan: MonthPlan, folder: str | Path, recipient: str = "") -> str:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / f"rueckmeldung_{plan.year}_{plan.month:02d}.html"
    out.write_text(render_form(plan, recipient), encoding="utf-8")
    return str(out)
