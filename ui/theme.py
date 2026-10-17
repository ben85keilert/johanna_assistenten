"""Zentrales Theme: Groessen UND Farbschema an EINER Stelle.

Das Programm gehoert nutzerfreundlich gestaltet (siehe BESCHREIBUNG.md):
gut klickbare Bedienelemente und lesbare Schrift - zugleich kompakt genug,
dass ein ganzer Monat auf den Bildschirm passt.
Wer die Oberflaeche vergroessern/verkleinern will, aendert die Werte hier.

Farbschema: vier Paletten (PALETTES), jede in einer hellen und einer
dunklen Variante; gewaehlt unter Einstellungen > Farbschema. Alle
Oberflaechenfarben (Fenster, Tabellen, Wochenend-Grau, Hinweistexte ...)
kommen aus colors() - nie fest im Code verdrahten. Die Farben der
Eintragsarten (VOLL, Tag, Nacht, RB, Urlaub, Wunsch) sind davon unabhaengig
und bleiben unter Einstellungen > Farben einstellbar.
"""
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor, QPalette, QPixmap, QPainter, QIcon
from PySide6.QtWidgets import QStyleFactory

# Grundschrift der ganzen Anwendung (Punkt)
FONT_PT = 10

# Notizsymbol: im Tageskopf und in den Zellen aller an dem Tag aktiven
# Helfer (Dienst und Rufbereitschaft)
NOTE_ICON = "\U0001F4DD"

# Zeichen fuer Wunsch-Tage (Freiwuensche) im Planraster. Bewusst
# unaufgeregt; Alternative: "" (kein Zeichen, nur die Wunsch-Farbe)
WISH_MARK = "/"

# Zeilenhoehe der Tabellen (Pixel)
ROW_HEIGHT = 32
# Team-Tab: etwas groesser (Zeilen, Schrift, Spalten), damit die
# abwechselnd gefaerbten Zeilen gut lesbar sind
TEAM_ROW_HEIGHT = 42
TEAM_FONT_PT = FONT_PT + 1
TEAM_NAME_COL_W = 170

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


@dataclass(frozen=True)
class ColorScheme:
    """Oberflaechenfarben einer Palettenvariante (Hex-Strings)."""
    window: str       # Fensterhintergrund
    surface: str      # Tabellen, Listen, Eingabefelder; leere Planzellen
    alt: str          # Kopfzeilen, Steuerleiste
    button: str       # Buttons, nicht gewaehlte Reiter
    text: str
    muted: str        # Nebentexte (Notizzeile, Hinweise)
    border: str       # Rahmen, Gitterlinien
    accent: str       # aktive Stempel, Auswahl, gewaehlter Reiter
    accent_text: str  # Text auf accent
    warning: str      # Warnhinweise unter dem Raster
    weekend: str      # Wochenenden + Feiertage (Raster, Urlaubs-Kalender)
    separator: str    # graue Kopfzeilen der geteilten Ansicht
    outside: str      # Kalendertage ausserhalb des Monats
    dark: bool = False


@dataclass(frozen=True)
class Palette:
    name: str         # Anzeigename im Menue
    light: ColorScheme
    dark: ColorScheme


PALETTES = {
    "ozean": Palette(
        "Ozean (Blau)",
        light=ColorScheme(
            window="#F3F6FA", surface="#FFFFFF", alt="#E6EDF5",
            button="#E9EEF4", text="#1E2A36", muted="#5C6B7A",
            border="#B9C5D1", accent="#2D7DD2", accent_text="#FFFFFF",
            warning="#B05000", weekend="#E4E9EF", separator="#D2DBE5",
            outside="#EEF1F5",
        ),
        dark=ColorScheme(
            window="#1B2229", surface="#232C35", alt="#2A3540",
            button="#2F3B47", text="#E3E9EF", muted="#9AA8B6",
            border="#465462", accent="#5AA4EC", accent_text="#0E1620",
            warning="#F0A050", weekend="#2E3740", separator="#37424D",
            outside="#1F262D", dark=True,
        ),
    ),
    "salbei": Palette(
        "Salbei (Gruen)",
        light=ColorScheme(
            window="#F4F6F2", surface="#FFFFFF", alt="#E7EDE3",
            button="#EAEFE6", text="#23301F", muted="#5F6B5A",
            border="#BCC7B5", accent="#4F8A4B", accent_text="#FFFFFF",
            warning="#A85A00", weekend="#E6EAE2", separator="#D3DBCD",
            outside="#F0F3EE",
        ),
        dark=ColorScheme(
            window="#1C211B", surface="#242B23", alt="#2C352A",
            button="#313B2F", text="#E4EAE1", muted="#A0AC9B",
            border="#48543F", accent="#86BC7F", accent_text="#142012",
            warning="#E8A55A", weekend="#2F362D", separator="#3A4437",
            outside="#1F251E", dark=True,
        ),
    ),
    "sand": Palette(
        "Sand (Terrakotta)",
        light=ColorScheme(
            window="#F8F4EE", surface="#FFFDF9", alt="#F0E8DC",
            button="#F1EADF", text="#3A2E22", muted="#75675A",
            border="#D2C4B1", accent="#B9592F", accent_text="#FFFFFF",
            warning="#A04000", weekend="#ECE5DB", separator="#DDD2C3",
            outside="#F4EFE8",
        ),
        dark=ColorScheme(
            window="#231D18", surface="#2C2520", alt="#352D26",
            button="#3A3129", text="#EFE6DC", muted="#B3A595",
            border="#584B3E", accent="#E38D62", accent_text="#22160F",
            warning="#F0B060", weekend="#372F28", separator="#433A31",
            outside="#26201B", dark=True,
        ),
    ),
    "lavendel": Palette(
        "Lavendel (Violett)",
        light=ColorScheme(
            window="#F6F4FA", surface="#FFFFFF", alt="#ECE8F4",
            button="#EEEAF5", text="#2B2438", muted="#686078",
            border="#C6BED7", accent="#6E52B5", accent_text="#FFFFFF",
            warning="#A85000", weekend="#E9E6F0", separator="#D8D2E4",
            outside="#F2F0F7",
        ),
        dark=ColorScheme(
            window="#1E1B26", surface="#27232F", alt="#302B3A",
            button="#352F41", text="#E8E4F0", muted="#A9A1B8",
            border="#4E4661", accent="#A58FE4", accent_text="#1A1426",
            warning="#F0A860", weekend="#322D3C", separator="#3D3748",
            outside="#211E29", dark=True,
        ),
    ),
}
DEFAULT_PALETTE = "ozean"

# Aktuell aktive Variante - apply_theme() setzt sie, colors() liest sie
_active: ColorScheme = PALETTES[DEFAULT_PALETTE].light


def colors() -> ColorScheme:
    """Farben des aktiven Farbschemas (zum Zeichnen immer frisch abfragen,
    damit ein Wechsel unter Einstellungen > Farbschema sofort greift)."""
    return _active


def scheme_for(palette: str, dark: bool) -> ColorScheme:
    entry = PALETTES.get(palette, PALETTES[DEFAULT_PALETTE])
    return entry.dark if dark else entry.light


def blend(color: QColor, alpha: int, base: QColor) -> QColor:
    """Farbe mit Deckkraft alpha (0-255) auf base - ergibt die sichtbare,
    deckende Mischfarbe (z. B. fuer die Wahl der Schriftfarbe)."""
    a = alpha / 255.0
    return QColor(
        round(color.red() * a + base.red() * (1 - a)),
        round(color.green() * a + base.green() * (1 - a)),
        round(color.blue() * a + base.blue() * (1 - a)),
    )


def stripe(c: ColorScheme) -> str:
    """Farbe jeder zweiten Tabellenzeile: ein Hauch der Akzentfarbe auf der
    Flaeche - so passt die Streifung zum Ton der Palette."""
    return blend(QColor(c.accent), 34 if c.dark else 24, QColor(c.surface)).name()


def text_on(background: QColor) -> QColor:
    """Gut lesbare Schriftfarbe (fast schwarz/fast weiss) auf background."""
    luminance = (0.299 * background.red() + 0.587 * background.green()
                 + 0.114 * background.blue())
    return QColor("#1A1A1A") if luminance > 140 else QColor("#F4F4F4")


def swatch_icon(scheme: ColorScheme) -> QIcon:
    """Kleines Vorschaubild einer Variante: Fenster, Flaeche, Akzent."""
    pixmap = QPixmap(36, 16)
    pixmap.fill(QColor(scheme.window))
    painter = QPainter(pixmap)
    painter.fillRect(2, 2, 14, 12, QColor(scheme.surface))
    painter.fillRect(18, 2, 16, 12, QColor(scheme.accent))
    painter.setPen(QColor(scheme.border))
    painter.drawRect(0, 0, 35, 15)
    painter.end()
    return QIcon(pixmap)


def _shade(hex_color: str, dark: bool, amount: int) -> str:
    """Hover-/Druckfarbe: im hellen Schema abdunkeln, im dunklen aufhellen."""
    color = QColor(hex_color)
    return (color.lighter(100 + amount) if dark else color.darker(100 + amount)).name()


def _stylesheet(c: ColorScheme) -> str:
    hover = _shade(c.button, c.dark, 8)
    pressed = _shade(c.button, c.dark, 18)
    # Akzent: Rand und Hover hell abgedunkelt, dunkel aufgehellt
    accent_edge = _shade(c.accent, c.dark, 15)
    accent_hover = _shade(c.accent, c.dark, 8)
    return f"""
QPushButton {{
    min-height: {BUTTON_HEIGHT}px;
    padding: 2px 8px;
    color: {c.text};
    background-color: {c.button};
    border: 1px solid {c.border};
    border-radius: 5px;
}}
QPushButton:hover {{
    background-color: {hover};
    border-color: {c.accent};
}}
QPushButton:pressed {{
    background-color: {pressed};
}}
QPushButton:checked {{
    background-color: {c.accent};
    color: {c.accent_text};
    border-color: {accent_edge};
}}
QPushButton:disabled {{
    color: {c.muted};
    background-color: {c.window};
}}
QPushButton[role="primary"] {{
    color: {c.accent_text};
    background-color: {c.accent};
    border: 1px solid {accent_edge};
    font-weight: bold;
    padding: 4px 18px;
}}
QPushButton[role="primary"]:hover {{
    background-color: {accent_hover};
}}
QSpinBox, QDateEdit, QComboBox {{
    min-height: {BUTTON_HEIGHT - 4}px;
}}
QSpinBox::up-button, QSpinBox::down-button,
QDateEdit::up-button, QDateEdit::down-button {{
    width: 22px;
}}
QTabWidget::pane {{
    border: 1px solid {c.border};
    border-radius: 4px;
    top: -1px;
}}
QTabBar::tab {{
    min-height: {BUTTON_HEIGHT}px;
    padding: 4px 14px;
    color: {c.text};
    background-color: {c.button};
    border: 1px solid {c.border};
    border-bottom: none;
    border-top-left-radius: 5px;
    border-top-right-radius: 5px;
    margin-right: 2px;
}}
QTabBar::tab:selected {{
    background-color: {c.surface};
    border-top: 3px solid {c.accent};
}}
QTabBar::tab:!selected:hover {{
    background-color: {hover};
}}
QHeaderView::section {{
    padding: 2px;
    color: {c.text};
    background-color: {c.alt};
    border: none;
    border-right: 1px solid {c.border};
    border-bottom: 1px solid {c.border};
}}
QTableCornerButton::section {{
    background-color: {c.alt};
    border: none;
}}
QTableView {{
    gridline-color: {c.border};
}}
QGroupBox {{
    border: 1px solid {c.border};
    border-radius: 6px;
    margin-top: 8px;
    padding: 2px 4px 2px 4px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 4px;
    color: {c.accent};
}}
QFrame#controlBar {{
    background-color: {c.alt};
    border: none;
    border-bottom: 1px solid {c.border};
}}
QLabel[role="muted"] {{
    color: {c.muted};
}}
QLabel[role="warning"] {{
    color: {c.warning};
}}
QToolTip {{
    color: {c.text};
    background-color: {c.surface};
    border: 1px solid {c.border};
    padding: 3px;
}}
"""


def _qpalette(c: ColorScheme) -> QPalette:
    pal = QPalette()
    role = QPalette.ColorRole
    for r, value in [
        (role.Window, c.window), (role.WindowText, c.text),
        (role.Base, c.surface), (role.AlternateBase, stripe(c)),
        (role.ToolTipBase, c.surface), (role.ToolTipText, c.text),
        (role.PlaceholderText, c.muted), (role.Text, c.text),
        (role.Button, c.button), (role.ButtonText, c.text),
        (role.BrightText, c.warning), (role.Highlight, c.accent),
        (role.HighlightedText, c.accent_text), (role.Link, c.accent),
        (role.Light, _shade(c.button, True, 12)),
        (role.Midlight, _shade(c.button, True, 5)),
        (role.Mid, c.border), (role.Dark, _shade(c.border, False, 20)),
        (role.Shadow, "#000000"),
    ]:
        pal.setColor(r, QColor(value))
    disabled = QPalette.ColorGroup.Disabled
    for r in (role.WindowText, role.Text, role.ButtonText):
        pal.setColor(disabled, r, QColor(c.muted))
    return pal


def apply_theme(app, palette: str = DEFAULT_PALETTE, dark: bool = False) -> None:
    """Schrift, Groessen und Farbschema auf die ganze Anwendung anwenden.

    Fusion als Grundstil, weil nur er die Palette auf allen Plattformen
    vollstaendig umsetzt (auch dunkel unter Windows). Mehrfach aufrufbar:
    ein Wechsel des Farbschemas greift sofort."""
    global _active
    _active = scheme_for(palette, dark)

    font = QFont()
    font.setPointSize(FONT_PT)
    app.setFont(font)
    fusion = QStyleFactory.create("Fusion")
    if fusion is not None:
        app.setStyle(fusion)
    app.setPalette(_qpalette(_active))
    app.setStyleSheet(_stylesheet(_active))
    # Fensterrahmen (Titelleiste) passend hell/dunkel - ab Qt 6.8
    try:
        app.styleHints().setColorScheme(
            Qt.ColorScheme.Dark if dark else Qt.ColorScheme.Light
        )
    except AttributeError:
        pass
