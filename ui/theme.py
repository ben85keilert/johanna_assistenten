"""Zentrales Theme: Schrift- und Klickflaechen-Groessen an EINER Stelle.

Das Programm gehoert nutzerfreundlich gestaltet (siehe BESCHREIBUNG.md):
grosse, gut klickbare Bedienelemente, grosse Schrift, grosse Zeilen.
Wer die Oberflaeche vergroessern/verkleinern will, aendert die Werte hier.
"""
from PySide6.QtGui import QFont

# Grundschrift der ganzen Anwendung (Punkt)
FONT_PT = 12

# Zeilenhoehe der Tabellen (Pixel)
ROW_HEIGHT = 44

# Normale Buttons (Pixel)
BUTTON_HEIGHT = 36

# Plus/Minus-Buttons der Stepper (nebeneinander, Pixel)
STEPPER_BUTTON_W = 44
STEPPER_BUTTON_H = 40

# Zentrale Steuerleiste unter dem Menue: bewusst uebertrieben gross
CONTROL_BAR_BUTTON_W = 96
CONTROL_BAR_BUTTON_H = 64
CONTROL_BAR_FONT_PT = 18

STYLESHEET = f"""
QPushButton {{
    min-height: {BUTTON_HEIGHT}px;
    padding: 4px 12px;
}}
QPushButton:checked {{
    background-color: #2D7DD2;
    color: white;
}}
QSpinBox, QDateEdit, QComboBox {{
    min-height: {BUTTON_HEIGHT - 4}px;
}}
QSpinBox::up-button, QSpinBox::down-button,
QDateEdit::up-button, QDateEdit::down-button {{
    width: 30px;
}}
QDateEdit::drop-down, QComboBox::drop-down {{
    width: 34px;
}}
QTabBar::tab {{
    min-height: {BUTTON_HEIGHT}px;
    padding: 6px 24px;
}}
QHeaderView::section {{
    padding: 4px;
}}
QGroupBox {{
    border: 1px solid #9a9a9a;
    border-radius: 8px;
    margin-top: 10px;
    padding: 4px 6px 2px 6px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 4px;
}}
"""


def apply_theme(app) -> None:
    font = QFont()
    font.setPointSize(FONT_PT)
    app.setFont(font)
    app.setStyleSheet(STYLESHEET)
