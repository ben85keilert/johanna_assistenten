from PySide6.QtWidgets import (
    QMainWindow, QTabWidget, QStatusBar, QWidget, QVBoxLayout, QStackedWidget
)
from PySide6.QtCore import Qt

from .control_bar import ControlBar
from .widgets.big_stepper import BigStepper
from version import __version__


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Johanna Assistenten v{__version__} - Dienstplan")
        self.setGeometry(100, 100, 1200, 800)

        self.is_modified = False
        self._title_plan = ""

        self.tab_widget = QTabWidget()

        # Dynamische Leiste in der Tab-Zeile: zeigt je nach aktivem Tab
        # dessen top_bar (Dienstplan: Jahr/Monat/Ansicht, Team: Urlaubsfilter)
        self._corner_stack = QStackedWidget()
        self._corner_pages = {}  # tab -> top_bar
        self.tab_widget.setCornerWidget(self._corner_stack, Qt.Corner.TopRightCorner)
        self.tab_widget.currentChanged.connect(self._sync_corner_bar)

        # Zentrale Werte-Steuerleiste zwischen Menue und Tabs
        self.control_bar = ControlBar(self._steppers_in_current_tab)
        BigStepper.activate_hook = self.control_bar.set_target
        self.tab_widget.currentChanged.connect(lambda _: self.control_bar._refresh())

        central = QWidget()
        central_layout = QVBoxLayout()
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(self.control_bar)
        central_layout.addWidget(self.tab_widget)
        central.setLayout(central_layout)
        self.setCentralWidget(central)

        self.team_tab = None
        self.plan_tab = None
        self.absence_tab = None

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Bereit")

        # Menue wird in main.py verdrahtet

        # Beim Schliessen fragt/speichert JohannaApp (siehe main.py).
        # Rueckgabe False = Schliessen abbrechen (Nutzer hat "Abbrechen"
        # gewaehlt oder das Speichern ist fehlgeschlagen)
        self.on_close_request = None

    def _steppers_in_current_tab(self) -> list[BigStepper]:
        current = self.tab_widget.currentWidget()
        if current is None:
            return []
        # Nur sichtbare Felder (im Team-Tab liegt je Vorlagen-Tab eine
        # eigene Tabelle - die inaktive soll nicht mitnavigiert werden)
        steppers = [s for s in current.findChildren(BigStepper) if s.isVisible()]
        # Leserichtung: von oben nach unten, links nach rechts
        def position(s):
            p = s.mapTo(current, s.rect().topLeft())
            return (p.y(), p.x())
        return sorted(steppers, key=position)

    def _register_top_bar(self, tab):
        # Tabs ohne eigene Kopfzeile bekommen eine leere Seite, damit in der
        # Tab-Ecke nicht die Bedienelemente des vorigen Tabs stehen bleiben
        page = getattr(tab, "top_bar", None) or QWidget()
        self._corner_pages[tab] = page
        self._corner_stack.addWidget(page)
        self._sync_corner_bar()

    def _sync_corner_bar(self, *_):
        page = self._corner_pages.get(self.tab_widget.currentWidget())
        if page is not None:
            self._corner_stack.setCurrentWidget(page)

    def set_plan_tab(self, tab):
        self.plan_tab = tab
        self.tab_widget.insertTab(0, tab, "Dienstplan")
        self.tab_widget.setCurrentIndex(0)
        self._register_top_bar(tab)

    def set_absence_tab(self, tab):
        self.absence_tab = tab
        self.tab_widget.addTab(tab, "Urlaub")
        self._register_top_bar(tab)

    def set_team_tab(self, tab):
        self.team_tab = tab
        self.tab_widget.addTab(tab, "Team")
        self._register_top_bar(tab)

    def set_title_plan(self, year: int, month: int):
        self._title_plan = f"Plan {year}-{month:02d}"
        self.update_window_title()

    def update_window_title(self):
        modified = "*" if self.is_modified else ""
        self.setWindowTitle(
            f"Johanna Assistenten v{__version__} - {self._title_plan}{modified}"
        )

    def mark_modified(self):
        self.is_modified = True
        self.update_window_title()

    def mark_saved(self):
        self.is_modified = False
        self.update_window_title()

    def closeEvent(self, event):
        if self.on_close_request is not None and not self.on_close_request():
            event.ignore()
            return
        event.accept()
