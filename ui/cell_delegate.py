from datetime import date

from PySide6.QtWidgets import (
    QStyledItemDelegate, QStyleOptionViewItem, QStyle, QToolTip,
)
from PySide6.QtCore import Qt, QRect, QSize
from PySide6.QtGui import QPainter, QColor, QFont, QPen

from PySide6.QtCore import QPoint

from models import ShiftType, is_effective, holiday_name
from scheduling.engine import is_on_vacation, is_blocked
from persistence import AppSettings
from . import theme

SHIFT_LABELS = {
    ShiftType.FULL: "VOLL",
    ShiftType.HALF_MORNING: "VM",
    ShiftType.HALF_AFTERNOON: "NM",
    ShiftType.ON_CALL: "RB",
}
# Schluessel in AppSettings.entry_colors je Dienstart
SHIFT_COLOR_KEYS = {
    ShiftType.FULL: "FULL",
    ShiftType.HALF_MORNING: "HALF_MORNING",
    ShiftType.HALF_AFTERNOON: "HALF_AFTERNOON",
    ShiftType.ON_CALL: "ON_CALL",
}
# Deckkraft nicht fixierter (gewuerfelter) Eintraege
GENERATED_ALPHA = 110
# Deckkraft nicht gewaehlter Kandidaten (nur Vorschlaege)
CANDIDATE_ALPHA = 50


class CellDelegate(QStyledItemDelegate):
    """Zeichnet die Planzellen direkt aus den Plandaten.

    Farblogik: jede Eintragsart (VOLL/VM/NM/RB/Urlaub/Block) hat ihre eigene,
    unter Einstellungen > Farben waehlbare Farbe. Feste Eintraege (von Hand
    gesetzt oder fixiert) sind kraeftig gefaerbt; noch in Planung befindliche
    (gewuerfelt, nicht fixiert) erscheinen transparent und tragen einen Punkt.
    Fixierte tragen ein Schloss, Urlaub ein "U", Block ein "X"."""

    def __init__(self, plan_provider, settings: AppSettings, parent=None):
        super().__init__(parent)
        # Callable statt Referenz, damit Monatswechsel automatisch greift
        self.plan_provider = plan_provider
        self.settings = settings

    def _entry_color(self, key: str) -> QColor:
        return QColor(self.settings.entry_colors.get(key, "#9E9E9E"))

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        plan = self.plan_provider()
        user_data = index.data(Qt.ItemDataRole.UserRole)
        if plan is None or not user_data:
            super().paint(painter, option, index)
            return

        assistant_id, day = user_data
        assistant = next((a for a in plan.assistants if a.id == assistant_id), None)
        entries = plan.schedule.get(day, [])
        entry = next((e for e in entries if e.assistant_id == assistant_id), None)
        # Urlaub hat Vorrang vor Block, falls beides gesetzt ist
        vacation = assistant is not None and is_on_vacation(
            assistant, day, plan.year, plan.month
        )
        blocked = (
            not vacation
            and assistant is not None
            and is_blocked(assistant, day, plan.year, plan.month)
        )
        # Wochenenden und bayerische Feiertage bekommen dieselbe graue
        # Grundflaeche (reine Anzeige, keine Planungslogik)
        gray_day = (
            date(plan.year, plan.month, day).weekday() >= 5
            or holiday_name(plan.year, plan.month, day) is not None
        )

        painter.save()

        # Kandidaten-Zustaende: unbewaehlter Vorschlag vs. getroffene Wahl
        is_open_candidate = entry is not None and entry.candidate and not entry.chosen
        # "In Planung": gewuerfelt oder vom Wuerfeln gewaehlter Kandidat,
        # jeweils noch nicht fixiert -> transparenter + Punkt
        in_planning = (
            entry is not None and not entry.locked
            and (entry.generated or (entry.candidate and entry.chosen))
        )

        # Grundflaeche (weiss bzw. Wochenend-Grau), darueber die Typfarbe:
        # voll deckend bei festen Eintraegen, transparent bei gewuerfelten,
        # sehr blass bei nicht gewaehlten Kandidaten
        painter.fillRect(option.rect, theme.WEEKEND_COLOR if gray_day else QColor(255, 255, 255))
        if entry is not None:
            overlay = self._entry_color(SHIFT_COLOR_KEYS.get(entry.shift_type, ""))
            if is_open_candidate:
                overlay.setAlpha(CANDIDATE_ALPHA)
            elif in_planning:
                overlay.setAlpha(GENERATED_ALPHA)
            painter.fillRect(option.rect, overlay)
        elif vacation:
            painter.fillRect(option.rect, self._entry_color("VACATION"))
        elif blocked:
            painter.fillRect(option.rect, self._entry_color("BLOCK"))

        # Nicht gewaehlter Kandidat: gestrichelter Rahmen in der Typfarbe
        if is_open_candidate:
            pen = QPen(self._entry_color(
                SHIFT_COLOR_KEYS.get(entry.shift_type, "")
            ).darker(130), 2)
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(option.rect.adjusted(2, 2, -2, -2))

        # Text
        text = ""
        if entry is not None:
            text = SHIFT_LABELS.get(entry.shift_type, "")
            if is_open_candidate:
                text += "?"
        elif vacation:
            text = "U"
        elif blocked:
            text = "X"
        if text:
            font = QFont()
            font.setBold(entry is not None and not is_open_candidate)
            painter.setFont(font)
            painter.setPen(QColor(60, 60, 60) if entry is None or is_open_candidate
                           else QColor(0, 0, 0))
            painter.drawText(option.rect, Qt.AlignmentFlag.AlignCenter, text)

        # Punkt oben links: zufaellig vergeben/gewaehlt (noch nicht fixiert)
        if in_planning:
            painter.setBrush(QColor(80, 80, 80))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(option.rect.left() + 4, option.rect.top() + 4, 6, 6)

        # Ueberplanter Freiwunsch: wirksamer Eintrag auf eigenem Block-Tag
        # -> kleines Warn-Dreieck unten rechts in der Block-Farbe
        if entry is not None and is_effective(entry) and blocked:
            r = option.rect
            triangle = [
                QPoint(r.right() - 10, r.bottom() - 1),
                QPoint(r.right() - 1, r.bottom() - 10),
                QPoint(r.right() - 1, r.bottom() - 1),
            ]
            painter.setBrush(self._entry_color("BLOCK").darker(120))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPolygon(triangle)

        # Notizsymbol unten links: der Tag hat eine Notiz und diese Person
        # ist an dem Tag aktiv (Dienst oder Rufbereitschaft) - z. B.
        # "Dienst startet um 14:00 Uhr" betrifft alle Eingeteilten
        if (entry is not None and is_effective(entry)
                and (plan.notes.get(day) or "").strip()):
            note_rect = QRect(option.rect.left() + 2, option.rect.bottom() - 15, 14, 14)
            painter.setPen(QColor(0, 0, 0))
            painter.setFont(QFont("", 8))
            painter.drawText(note_rect, Qt.AlignmentFlag.AlignCenter, theme.NOTE_ICON)

        # Schloss oben rechts: fixiert
        if entry is not None and entry.locked:
            lock_rect = QRect(option.rect.right() - 16, option.rect.top() + 2, 14, 14)
            painter.setPen(QColor(0, 0, 0))
            painter.setFont(QFont("", 8))
            painter.drawText(lock_rect, Qt.AlignmentFlag.AlignCenter, "\U0001F512")

        # Auswahl-Markierung als Rahmen + leichte Tönung
        if option.state & QStyle.StateFlag.State_Selected:
            highlight = QColor(option.palette.highlight().color())
            highlight.setAlpha(60)
            painter.fillRect(option.rect, highlight)
            pen = QPen(option.palette.highlight().color(), 2)
            painter.setPen(pen)
            painter.drawRect(option.rect.adjusted(1, 1, -1, -1))

        painter.restore()

    def helpEvent(self, event, view, option, index) -> bool:
        """Tooltip mit dem Notiztext auf Zellen mit Notizsymbol."""
        plan = self.plan_provider()
        user_data = index.data(Qt.ItemDataRole.UserRole)
        if plan is not None and user_data:
            assistant_id, day = user_data
            note = (plan.notes.get(day) or "").strip()
            entry = next(
                (e for e in plan.schedule.get(day, [])
                 if e.assistant_id == assistant_id), None,
            )
            if note and entry is not None and is_effective(entry):
                QToolTip.showText(event.globalPos(), f"{theme.NOTE_ICON} {note}", view)
                return True
        return super().helpEvent(event, view, option, index)

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        return QSize(theme.DAY_COL_MIN_W, theme.ROW_HEIGHT)
