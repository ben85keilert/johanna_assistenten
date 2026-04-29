from PySide6.QtWidgets import QPushButton, QColorDialog
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtCore import Signal, Qt


class ColorButton(QPushButton):
    color_changed = Signal(str)

    def __init__(self, color: str, parent=None):
        super().__init__(parent)
        self.current_color = color
        self.set_color(color)
        self.clicked.connect(self.pick_color)
        self.setMaximumWidth(60)

    def set_color(self, color: str):
        self.current_color = color
        pixmap = QPixmap(40, 40)
        pixmap.fill(QColor(color))
        self.setIcon(pixmap)
        self.setIconSize(pixmap.size())

    def pick_color(self):
        color = QColorDialog.getColor(
            QColor(self.current_color),
            self,
            "Farbe auswaehlen"
        )
        if color.isValid():
            hex_color = color.name()
            self.set_color(hex_color)
            self.color_changed.emit(hex_color)
