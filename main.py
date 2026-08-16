import sys
from datetime import datetime

from PySide6.QtWidgets import QApplication, QMessageBox, QFileDialog
from PySide6.QtCore import QByteArray
from PySide6.QtGui import QAction

from models import MonthPlan
from persistence import (
    save, load, save_team, load_team, save_plan, load_plan,
    load_profiles, load_settings, save_settings,
)
from ui.main_window import MainWindow
from ui.team_tab import TeamTab
from ui.plan_tab import PlanTab
from ui.theme import apply_theme


class JohannaApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        apply_theme(self.app)
        self.settings = load_settings()
        self.window = MainWindow()
        self.plan = self._auto_load()
        # Die zwei Einstellungs-Vorlagen (Team-Tab) gelten monatsuebergreifend
        self.profiles = load_profiles()

        self.team_tab = TeamTab()
        self.team_tab.set_profiles(self.profiles)
        self.plan_tab = PlanTab(self.settings)

        self.window.set_plan_tab(self.plan_tab)
        self.window.set_team_tab(self.team_tab)

        self.setup_menu()

        # Signale verdrahten: Aenderungen sofort in beiden Tabs sichtbar
        self.team_tab.assistants_changed.connect(self.plan_tab.rebuild_grid)
        self.team_tab.assistants_changed.connect(self.window.mark_modified)
        self.team_tab.profiles_changed.connect(self.window.mark_modified)
        self.plan_tab.plan_modified.connect(self.window.mark_modified)
        self.plan_tab.constraints_changed.connect(self.team_tab.refresh_all)
        self.plan_tab.month_change_requested.connect(self.change_month)
        self.window.on_close_save = self.autosave_on_close

        self.load_plan_to_ui()
        self._restore_geometry()

    def _auto_load(self) -> MonthPlan:
        # Letzten Zustand wiederherstellen: zuletzt geoeffneter Monat,
        # sonst der aktuelle Kalendermonat
        now = datetime.now()
        year = self.settings.last_year or now.year
        month = self.settings.last_month or now.month

        assistants = load_team()
        plan = load_plan(year, month, assistants)
        if plan is None:
            plan = MonthPlan(year=year, month=month, assistants=assistants)
        return plan

    def _restore_geometry(self):
        if self.settings.window_geometry:
            geometry = QByteArray.fromHex(self.settings.window_geometry.encode())
            if not geometry.isEmpty():
                self.window.restoreGeometry(geometry)

    def setup_menu(self):
        menubar = self.window.menuBar()
        file_menu = menubar.addMenu("Datei")

        new_action = QAction("Monat leeren", self.window)
        new_action.triggered.connect(self.clear_month)
        file_menu.addAction(new_action)

        open_action = QAction("Plan-Datei oeffnen...", self.window)
        open_action.triggered.connect(self.open_plan)
        file_menu.addAction(open_action)

        save_action = QAction("Speichern", self.window)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self.save_all)
        file_menu.addAction(save_action)

        export_menu = file_menu.addMenu("Exportieren")
        for label, handler in [
            ("CSV", self.export_csv),
            ("Excel", self.export_excel),
            ("PDF", self.export_pdf),
        ]:
            action = QAction(label, self.window)
            action.triggered.connect(handler)
            export_menu.addAction(action)

        file_menu.addSeparator()

        exit_action = QAction("Beenden", self.window)
        exit_action.triggered.connect(self.window.close)
        file_menu.addAction(exit_action)

    def load_plan_to_ui(self):
        self.team_tab.set_plan(self.plan)
        self.plan_tab.set_plan(self.plan)
        self.window.set_title_plan(self.plan.year, self.plan.month)
        self.window.mark_saved()

    def change_month(self, year: int, month: int):
        """Monatswechsel: aktuellen Monat speichern, Zielmonat laden."""
        if (year, month) == (self.plan.year, self.plan.month):
            return

        self._save_current(update_status=False)

        assistants = load_team()
        plan = load_plan(year, month, assistants)
        if plan is None:
            plan = MonthPlan(year=year, month=month, assistants=assistants)
        self.plan = plan

        self.settings.last_year = year
        self.settings.last_month = month
        self.load_plan_to_ui()

    def clear_month(self):
        reply = QMessageBox.question(
            self.window,
            "Monat leeren",
            f"Alle Eintraege fuer {self.plan.year}-{self.plan.month:02d} loeschen?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.plan.schedule.clear()
            self.plan_tab.rebuild_grid()
            self.window.mark_modified()

    def open_plan(self):
        path, _ = QFileDialog.getOpenFileName(
            self.window, "Plan oeffnen", filter="JSON-Dateien (*.json)"
        )
        if path:
            try:
                self.plan = load(path)
                self.settings.last_year = self.plan.year
                self.settings.last_month = self.plan.month
                self.load_plan_to_ui()
                self.window.status_bar.showMessage(f"Geladen: {path}")
            except Exception as e:
                QMessageBox.critical(self.window, "Fehler", f"Laden fehlgeschlagen:\n{e}")

    def _save_current(self, update_status: bool = True):
        self.plan.modified_at = datetime.now().isoformat()
        if not self.plan.created_at:
            self.plan.created_at = datetime.now().isoformat()
        save_team(self.plan.assistants, self.profiles)
        save_plan(self.plan)
        self.window.mark_saved()
        if update_status:
            self.window.status_bar.showMessage(
                f"Gespeichert: Plan {self.plan.year}-{self.plan.month:02d}"
            )

    def save_all(self):
        try:
            self._save_current()
            self._save_settings()
        except Exception as e:
            QMessageBox.critical(self.window, "Fehler", f"Speichern fehlgeschlagen:\n{e}")

    def _save_settings(self):
        self.settings.last_year = self.plan.year
        self.settings.last_month = self.plan.month
        self.settings.window_geometry = bytes(
            self.window.saveGeometry().toHex()
        ).decode()
        save_settings(self.settings)

    def autosave_on_close(self):
        # Beim Beenden wird automatisch gespeichert (Session-Restore beim
        # naechsten Start); Fehler duerfen das Schliessen nicht verhindern
        try:
            self._save_current(update_status=False)
            self._save_settings()
        except Exception as e:
            print(f"Automatisches Speichern fehlgeschlagen: {e}", file=sys.stderr)

    def export_csv(self):
        folder = QFileDialog.getExistingDirectory(self.window, "Zielordner waehlen")
        if folder:
            try:
                from export.csv_exporter import export_csv
                f1, f2 = export_csv(self.plan, folder)
                QMessageBox.information(
                    self.window, "Erfolg", f"CSV exportiert:\n{f1}\n{f2}"
                )
            except Exception as e:
                QMessageBox.critical(self.window, "Fehler", f"Export fehlgeschlagen:\n{e}")

    def export_excel(self):
        folder = QFileDialog.getExistingDirectory(self.window, "Zielordner waehlen")
        if folder:
            try:
                from export.excel_exporter import export_excel
                f = export_excel(self.plan, folder)
                QMessageBox.information(self.window, "Erfolg", f"Excel exportiert:\n{f}")
            except Exception as e:
                QMessageBox.critical(self.window, "Fehler", f"Export fehlgeschlagen:\n{e}")

    def export_pdf(self):
        folder = QFileDialog.getExistingDirectory(self.window, "Zielordner waehlen")
        if folder:
            try:
                from export.pdf_exporter import export_pdf
                f = export_pdf(self.plan, folder)
                QMessageBox.information(self.window, "Erfolg", f"PDF exportiert:\n{f}")
            except Exception as e:
                QMessageBox.critical(self.window, "Fehler", f"Export fehlgeschlagen:\n{e}")

    def run(self):
        self.window.show()
        return self.app.exec()


if __name__ == "__main__":
    app = JohannaApp()
    sys.exit(app.run())
