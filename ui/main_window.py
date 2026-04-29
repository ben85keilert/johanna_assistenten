from PySide6.QtWidgets import (
    QMainWindow,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QStatusBar,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon

from models import MonthPlan
from persistence import save, load


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Johanna Assistenten - Dienstplan")
        self.setGeometry(100, 100, 1200, 800)

        self.current_plan: MonthPlan | None = None
        self.current_file_path: str | None = None
        self.is_modified = False

        # Tab-Widget
        self.tab_widget = QTabWidget()
        self.setCentralWidget(self.tab_widget)

        # Placeholder für Tabs (werden später verdrahtet)
        self.team_tab = None
        self.plan_tab = None

        # Statusbar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Bereit")

        # Menü wird in main.py verdrahtet

    def set_team_tab(self, tab):
        self.team_tab = tab
        self.tab_widget.addTab(tab, "Team")

    def set_plan_tab(self, tab):
        self.plan_tab = tab
        self.tab_widget.addTab(tab, "Dienstplan")

    def update_window_title(self):
        if self.current_file_path:
            path_display = self.current_file_path.split("/")[-1]
        else:
            path_display = "Unbenannt"

        modified = "*" if self.is_modified else ""
        self.setWindowTitle(f"Johanna Assistenten - {path_display}{modified}")

    def mark_modified(self):
        self.is_modified = True
        self.update_window_title()

    def mark_saved(self):
        self.is_modified = False
        self.update_window_title()

    def closeEvent(self, event):
        if self.is_modified:
            from PySide6.QtWidgets import QMessageBox

            reply = QMessageBox.question(
                self,
                "Nicht gespeicherte Aenderungen",
                "Moechten Sie die Aenderungen speichern?",
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Save:
                # Speichern-Logik wird verdrahtet
                event.accept()
            elif reply == QMessageBox.StandardButton.Discard:
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()
