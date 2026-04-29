from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QStyle
from PySide6.QtCore import Qt, QRect, QSize
from PySide6.QtGui import QPainter, QColor, QFont, QIcon, QPixmap

from models import MonthPlan


class CellDelegate(QStyledItemDelegate):
    def __init__(self, plan: MonthPlan, parent=None):
        super().__init__(parent)
        self.plan = plan

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        # Hintergrund zeichnen
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
        else:
            painter.fillRect(option.rect, option.palette.base())

        # Text zeichnen
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        if text:
            font = QFont()
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(option.rect, Qt.AlignmentFlag.AlignCenter, text)

            # Schloss-Icon wenn gesperrt
            user_data = index.data(Qt.ItemDataRole.UserRole)
            if user_data:
                assistant_id, day = user_data
                entries = self.plan.schedule.get(day, [])
                matching = [e for e in entries if e.assistant_id == assistant_id]
                if matching and matching[0].locked:
                    # Kleines Schloss-Icon in der Ecke
                    lock_rect = QRect(
                        option.rect.right() - 16,
                        option.rect.top(),
                        16, 16
                    )
                    painter.fillRect(lock_rect, QColor(255, 200, 200, 100))
                    painter.drawText(lock_rect, Qt.AlignmentFlag.AlignCenter, "L")

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        return QSize(60, 40)
