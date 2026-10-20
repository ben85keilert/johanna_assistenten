"""Maschinenzeile des Rueckmeldeformulars lesen.

Das Formular (vorlagen/rueckmeldung.html) haengt an den Mailtext eine Zeile

    JA1;2026-11;8cdf0de4;T:2026-10-20T14:03:05;U:3,10-14;W:5,6;D:7-9;N:Am%2012.;END

Format-Kennung, Monat, Helfer-ID, Zeitstempel des Formulars (T, lokale
Zeit - "welcher Stand ist das?"), dann Urlaub (U), Wunsch frei (W) und
Dienstwunsch (D) als Tageslisten mit Bereichen, die Bemerkung URL-kodiert
(N) und das Ende-Zeichen END. Zwischen "JA1;" und ";END" steht nichts, was
ein Leerzeichen, einen Zeilenumbruch oder ein ">" enthalten koennte -
deshalb duerfen Mailprogramme die Zeile umbrechen oder zitieren, der Parser
wirft Leerraum und Zitatzeichen im Block einfach weg. Alles ausserhalb des
Blocks (Grussformel, Signatur, zitierte Mails) ist egal, und ein Text darf
mehrere Bloecke enthalten (mehrere Mails auf einmal eingefuegt).

Kein Raten, keine KI: eine Zeile ist entweder vollstaendig gueltig oder
wird mit Begruendung abgelehnt.
"""
from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, field
from datetime import datetime
from email import policy
from email.parser import BytesParser
from html import unescape
from pathlib import Path
from urllib.parse import unquote

FORMAT_ID = "JA1"
END_MARK = "END"

# Schluessel der Tagesarten im Format -> models.DAY_KINDS
KIND_CODES = {"U": "urlaub", "W": "block", "D": "wish"}
KIND_LABELS = {"urlaub": "Urlaub", "block": "Wunsch frei", "wish": "Dienstwunsch"}

_BLOCK = re.compile(FORMAT_ID + r";.*?;" + END_MARK, re.S)
_NOISE = re.compile(r"[\s>]+")
# Alte Fassung ohne END (erste Vorlage): bis zum Zeilenende lesen
_BLOCK_LEGACY = re.compile(FORMAT_ID + r";\d{4}-\d{2};[^\s<>\"']+")


@dataclass
class Feedback:
    """Eine gelesene Rueckmeldung (oder ein Lesefehler)."""
    year: int = 0
    month: int = 0
    assistant_id: str = ""
    days: dict[str, set[int]] = field(default_factory=dict)   # kind -> Tage
    note: str = ""
    stamp: str = ""           # Zeitstempel aus dem Formular (ISO, "" = alte Fassung)
    source: str = ""          # woher (Datei, Zwischenablage)
    raw: str = ""             # der Block, wie gefunden
    error: str | None = None  # None = gueltig
    path: Path | None = None  # Datei im Ablageordner (fuer "eingelesen"-Merker)

    @property
    def ok(self) -> bool:
        return self.error is None

    def count(self, kind: str) -> int:
        return len(self.days.get(kind, ()))

    def month_key(self) -> str:
        return f"{self.year}-{self.month:02d}"


def format_stamp(stamp: str) -> str:
    """ISO-Zeitstempel lesbar: 20.10.2026 14:03 ("" bleibt leer)."""
    if not stamp:
        return ""
    try:
        return datetime.fromisoformat(stamp).strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return stamp


def extract_blocks(text: str) -> list[str]:
    """Alle Maschinenbloecke im Text, bereinigt (ohne Leerraum/Zitatzeichen).

    Erst wird der ganze Text von Leerraum und Zitatzeichen befreit - ein
    Block enthaelt beides nie, ein Umbruch mitten im Block (auch direkt vor
    END) stoert so nicht. Nur ohne Treffer gilt die alte Fassung ohne END."""
    compact = _NOISE.sub("", text)
    blocks = [m.group(0) for m in _BLOCK.finditer(compact)]
    if not blocks:
        blocks = [m.group(0) for m in _BLOCK_LEGACY.finditer(text)]
    # Dieselbe Zeile zweimal im Text (z. B. Mail + Zitat der Antwort): einmal
    seen, unique = set(), []
    for b in blocks:
        if b not in seen:
            seen.add(b)
            unique.append(b)
    return unique


def _parse_days(value: str, days_in_month: int, label: str) -> set[int]:
    result: set[int] = set()
    for chunk in filter(None, value.split(",")):
        a, sep, b = chunk.partition("-")
        if not a.isdigit() or (sep and not b.isdigit()):
            raise ValueError(f"{label}: unlesbare Tagesangabe '{chunk}'")
        start, end = int(a), int(b or a)
        if start > end or start < 1 or end > days_in_month:
            raise ValueError(f"{label}: Tag '{chunk}' liegt nicht im Monat")
        result.update(range(start, end + 1))
    return result


def parse_block(block: str, source: str = "") -> Feedback:
    fb = Feedback(source=source, raw=block)
    parts = block.split(";")
    try:
        if parts[-1] == END_MARK:
            parts = parts[:-1]
        if len(parts) < 3 or parts[0] != FORMAT_ID:
            raise ValueError("unbekanntes Format")
        year_s, _, month_s = parts[1].partition("-")
        if not (year_s.isdigit() and month_s.isdigit() and 1 <= int(month_s) <= 12):
            raise ValueError(f"ungueltiger Monat '{parts[1]}'")
        fb.year, fb.month = int(year_s), int(month_s)
        fb.assistant_id = parts[2].strip()
        if not fb.assistant_id:
            raise ValueError("Helfer-ID fehlt")
        days_in_month = calendar.monthrange(fb.year, fb.month)[1]
        fb.days = {kind: set() for kind in KIND_CODES.values()}
        for part in parts[3:]:
            code, sep, value = part.partition(":")
            if not sep:
                raise ValueError(f"unlesbarer Teil '{part}'")
            if code == "N":
                fb.note = unquote(value).strip()
            elif code == "T":
                try:
                    fb.stamp = datetime.fromisoformat(value).isoformat(timespec="seconds")
                except ValueError:
                    raise ValueError(f"unlesbarer Zeitstempel '{value}'")
            elif code in KIND_CODES:
                kind = KIND_CODES[code]
                fb.days[kind] = _parse_days(value, days_in_month, KIND_LABELS[kind])
            else:
                raise ValueError(f"unbekannter Teil '{code}'")
        all_days = [d for days in fb.days.values() for d in days]
        if len(all_days) != len(set(all_days)):
            raise ValueError("ein Tag ist mehrfach eingetragen")
    except ValueError as e:
        fb.error = str(e)
    return fb


def parse_text(text: str, source: str = "") -> list[Feedback]:
    return [parse_block(b, source) for b in extract_blocks(text)]


def read_file_text(path: Path) -> str:
    """Text einer Antwortdatei: .eml wird als Mail zerlegt (alle Textteile),
    .html von Tags befreit, alles andere als Text gelesen."""
    suffix = path.suffix.lower()
    if suffix == ".eml":
        with open(path, "rb") as f:
            msg = BytesParser(policy=policy.default).parse(f)
        parts = []
        for part in msg.walk():
            if part.get_content_type() in ("text/plain", "text/html"):
                try:
                    content = part.get_content()
                except Exception:
                    continue
                if part.get_content_type() == "text/html":
                    content = _strip_html(content)
                parts.append(content)
        return "\n".join(parts)
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    if suffix in (".html", ".htm"):
        text = _strip_html(text)
    return text


def _strip_html(html: str) -> str:
    # <br>/<p> werden Zeilenumbrueche, Tags fallen weg, Entities aufloesen
    html = re.sub(r"<\s*(br|/p|/div|/tr)\s*/?>", "\n", html, flags=re.I)
    html = re.sub(r"<[^>]+>", "", html)
    return unescape(html)
