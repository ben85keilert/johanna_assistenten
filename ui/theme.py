"""Zentrales Theme: Schrift- und Klickflaechen-Groessen an EINER Stelle.

Das Programm gehoert nutzerfreundlich gestaltet (siehe BESCHREIBUNG.md):
gut klickbare Bedienelemente und lesbare Schrift - zugleich kompakt genug,
dass ein ganzer Monat auf den Bildschirm passt.
Wer die Oberflaeche vergroessern/verkleinern will, aendert die Werte hier.
"""
from PySide6.QtGui import QFont, QColor

# Grundschrift der ganzen Anwendung (Punkt)
FONT_PT = 10

# Grau fuer Wochenenden UND bayerische Feiertage (models/holidays.py) -
# ueberall dieselbe Farbe: Planraster, Urlaubs-Kalender, PDF-Export
WEEKEND_COLOR = QColor(235, 235, 235)

# Notizsymbol: im Tageskopf und in den Zellen aller an dem Tag aktiven
# Helfer (Dienst und Rufbereitschaft)
NOTE_ICON = "\U0001F4DD"

# Zeilenhoehe der Tabellen (Pixel)
ROW_HEIGHT = 32

# Normale Buttons (Pixel)
BUTTON_HEIGHT = 28

# Plus/Minus-Buttons der Stepper (nebeneinander, Pixel)
STEPPER_BUTTON_W = 34
STEPPER_BUTTON_H = 28
# Wertanzeige zwischen den beiden Buttons
STEPPER_VALUE_W = 40
# Spaltenbreite fuer eine Tabellenzelle mit Stepper (Buttons + Wert + Raender)
STEPPER_WIDTH = 2 * STEPPER_BUTTON_W + STEPPER_VALUE_W + 16

# Mindestbreite einer Tagesspalte im Dienstplan
DAY_COL_MIN_W = 44

# Zentrale Steuerleiste unter dem Menue: bewusst groesser als der Rest
CONTROL_BAR_BUTTON_W = 72
CONTROL_BAR_BUTTON_H = 46
CONTROL_BAR_FONT_PT = 14

STYLESHEET = f"""
QPushButton {{
    min-height: {BUTTON_HEIGHT}px;
    padding: 2px 8px;
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
    width: 22px;
}}
QDateEdit::drop-down, QComboBox::drop-down {{
    width: 26px;
}}
QTabBar::tab {{
    min-height: {BUTTON_HEIGHT}px;
    padding: 4px 14px;
}}
QHeaderView::section {{
    padding: 2px;
}}
QGroupBox {{
    border: 1px solid #9a9a9a;
    border-radius: 6px;
    margin-top: 8px;
    padding: 2px 4px 2px 4px;
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
