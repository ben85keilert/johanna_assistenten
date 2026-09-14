"""Einstellungen > Farben: eine Farbe je Eintragsart.

Statt einer Farbe je Helfer (zu bunt) traegt jede Eintragsart im Planraster
einheitlich ihre eigene Farbe. Feste Eintraege erscheinen kraeftig, noch in
Planung befindliche (gewuerfelte) transparenter - die Vorschau rechts zeigt
beide Varianten. Aenderungen gelten erst mit OK; "Standardfarben" setzt auf
die Auslieferungswerte zurueck.
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
)
from PySide6.QtGui import QColor, QPixmap, QPainter

from persistence import AppSettings, DEFAULT_ENTRY_COLORS
from .widgets.color_button import ColorButton
from .cell_delegate import GENERATED_ALPHA

# Reihenfolge und Beschriftung der Eintragsarten im Dialog
ENTRY_TYPES = [
    ("FULL", "Tagesdienst (VOLL)"),
    ("HALF_MORNING", "Vormittag (VM)"),
    ("HALF_AFTERNOON", "Nachmittag (NM)"),
    ("ON_CALL", "Rufbereitschaft (RB)"),
    ("VACATION", "Urlaub"),
    ("BLOCK", "Block"),
]

_PREVIEW_W, _PREVIEW_H = 96, 24


def _preview_pixmap(color: str) -> QPixmap:
    """Linke Haelfte: fest (voll deckend), rechte: in Planung (transparent)."""
    pixmap = QPixmap(_PREVIEW_W, _PREVIEW_H)
    pixmap.fill(QColor(255, 255, 255))
    painter = QPainter(pixmap)
    full = QColor(color)
    painter.fillRect(0, 0, _PREVIEW_W // 2, _PREVIEW_H, full)
    transparent = QColor(color)
    transparent.setAlpha(GENERATED_ALPHA)
    painter.fillRect(_PREVIEW_W // 2, 0, _PREVIEW_W // 2, _PREVIEW_H, transparent)
    painter.setPen(QColor(150, 150, 150))
    painter.drawRect(0, 0, _PREVIEW_W - 1, _PREVIEW_H - 1)
    painter.end()
    return pixmap


class ColorSettingsDialog(QDialog):
    """Aendert bei OK settings.entry_colors direkt; Abbrechen laesst alles."""

    def __init__(self, settings: AppSettings, parent=None):
        super().__init__(parent)
        self.settings = settings
        # Arbeitskopie: erst OK uebertraegt die Auswahl
        self._colors = dict(settings.entry_colors)
        self.setWindowTitle("Farben der Eintragsarten")

        layout = QVBoxLayout()
        hint = QLabel(
            "Jede Eintragsart hat im Plan ihre eigene Farbe. Feste Eintraege "
            "sind kraeftig gefaerbt, noch in Planung befindliche (gewuerfelte) "
            "transparenter - die Vorschau zeigt links fest, rechts in Planung."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        grid = QGridLayout()
        self._previews = {}
        self._buttons = {}
        for row, (key, label) in enumerate(ENTRY_TYPES):
            grid.addWidget(QLabel(label), row, 0)
            button = ColorButton(self._colors.get(key, DEFAULT_ENTRY_COLORS[key]))
            button.color_changed.connect(
                lambda color, k=key: self._on_color_changed(k, color)
            )
            grid.addWidget(button, row, 1)
            preview = QLabel()
            preview.setPixmap(_preview_pixmap(self._colors.get(
                key, DEFAULT_ENTRY_COLORS[key]
            )))
            grid.addWidget(preview, row, 2)
            self._previews[key] = preview
            self._buttons[key] = button
        grid.setColumnStretch(3, 1)
        layout.addLayout(grid)

        buttons = QHBoxLayout()
        reset_btn = QPushButton("Standardfarben")
        reset_btn.setToolTip("Alle Farben auf die Auslieferungswerte zuruecksetzen.")
        reset_btn.clicked.connect(self._reset_defaults)
        buttons.addWidget(reset_btn)
        buttons.addStretch()
        ok_btn = QPushButton("OK")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept)
        buttons.addWidget(ok_btn)
        cancel_btn = QPushButton("Abbrechen")
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(cancel_btn)
        layout.addLayout(buttons)

        self.setLayout(layout)

    def _on_color_changed(self, key: str, color: str):
        self._colors[key] = color
        self._previews[key].setPixmap(_preview_pixmap(color))

    def _reset_defaults(self):
        for key, color in DEFAULT_ENTRY_COLORS.items():
            self._colors[key] = color
            if key in self._buttons:
                self._buttons[key].set_color(color)
                self._previews[key].setPixmap(_preview_pixmap(color))

    def accept(self):
        self.settings.entry_colors.update(self._colors)
        super().accept()
