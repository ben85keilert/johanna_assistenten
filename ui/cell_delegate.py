from datetime import date

from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QStyle
from PySide6.QtCore import Qt, QRect, QSize
from PySide6.QtGui import QPainter, QColor, QFont, QPen

from models import ShiftType
from scheduling.engine import is_unavailable

WEEKEND_COLOR = QColor(235, 235, 235)
UNAVAILABLE_COLOR = QColor(200, 200, 200)
SHIFT_LABELS = {
    ShiftType.FULL: "VOLL",
    ShiftType.HALF_MORNING: "VM",
    ShiftType.HALF_AFTERNOON: "NM",
}


class CellDelegate(QStyledItemDelegate):
    """Zeichnet die Planzellen direkt aus den Plandaten:
    Helferfarbe (heller + Punkt bei Zufallseintraegen), Schloss bei fixierten,
    grau mit "U" bei Urlaub/Abwesenheit, Wochenend-Grau."""

    def __init__(self, plan_provider, parent=None):
        super().__init__(parent)
        # Callable statt Referenz, damit Monatswechsel automatisch greift
        self.plan_provider = plan_provider

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
        unavailable = assistant is not None and is_unavailable(
            assistant, day, plan.year, plan.month
        )
        weekend = date(plan.year, plan.month, day).weekday() >= 5

        painter.save()

        # Hintergrund
        if entry is not None and assistant is not None:
            background = QColor(assistant.color)
            if entry.generated:
                background = background.lighter(150)
        elif unavailable:
            background = UNAVAILABLE_COLOR
        elif weekend:
            background = WEEKEND_COLOR
        else:
            background = QColor(255, 255, 255)
        painter.fillRect(option.rect, background)

        # Text
        text = ""
        if entry is not None:
            text = SHIFT_LABELS.get(entry.shift_type, "")
        elif unavailable:
            text = "U"
        if text:
            font = QFont()
            font.setBold(entry is not None)
            painter.setFont(font)
            painter.setPen(QColor(60, 60, 60) if entry is None else QColor(0, 0, 0))
            painter.drawText(option.rect, Qt.AlignmentFlag.AlignCenter, text)

        # Punkt oben links: zufaellig vergeben (noch nicht fixiert)
        if entry is not None and entry.generated and not entry.locked:
            painter.setBrush(QColor(80, 80, 80))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(option.rect.left() + 4, option.rect.top() + 4, 6, 6)

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

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        return QSize(60, 40)
