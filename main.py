import sys
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QMessageBox, QFileDialog,
    QVBoxLayout, QWidget
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction

from models import MonthPlan, Assistant, AssistantConstraints
from persistence import save, load
from datetime import datetime
import uuid
from ui.main_window import MainWindow
from ui.team_tab import TeamTab
from ui.plan_tab import PlanTab


class JohannaApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.window = MainWindow()
        self.plan = self.create_new_plan()

        self.team_tab = TeamTab()
        self.plan_tab = PlanTab()

        self.window.set_team_tab(self.team_tab)
        self.window.set_plan_tab(self.plan_tab)

        self.setup_menu()
        self.load_plan_to_ui()

    def create_new_plan(self) -> MonthPlan:
        now = datetime.now()
        plan = MonthPlan(year=now.year, month=now.month)

        # Dummy-Assistenten für Tests
        for i in range(3):
            aid = str(uuid.uuid4())[:8]
            constraints = AssistantConstraints(assistant_id=aid)
            assistant = Assistant(
                id=aid,
                name=f"Assistent {i+1}",
                color=["#E74C3C", "#3498DB", "#2ECC71"][i],
                constraints=constraints,
            )
            plan.assistants.append(assistant)

        return plan

    def setup_menu(self):
        menubar = self.window.menuBar()
        file_menu = menubar.addMenu("Datei")

        # Neu
        new_action = QAction("Neu", self.window)
        new_action.triggered.connect(self.new_plan)
        file_menu.addAction(new_action)

        # Oeffnen
        open_action = QAction("Oeffnen", self.window)
        open_action.triggered.connect(self.open_plan)
        file_menu.addAction(open_action)

        # Speichern
        save_action = QAction("Speichern", self.window)
        save_action.triggered.connect(self.save_plan)
        file_menu.addAction(save_action)

        # Exportieren
        export_menu = file_menu.addMenu("Exportieren")

        csv_action = QAction("CSV", self.window)
        csv_action.triggered.connect(self.export_csv)
        export_menu.addAction(csv_action)

        excel_action = QAction("Excel", self.window)
        excel_action.triggered.connect(self.export_excel)
        export_menu.addAction(excel_action)

        pdf_action = QAction("PDF", self.window)
        pdf_action.triggered.connect(self.export_pdf)
        export_menu.addAction(pdf_action)

        file_menu.addSeparator()

        # Beenden
        exit_action = QAction("Beenden", self.window)
        exit_action.triggered.connect(self.window.close)
        file_menu.addAction(exit_action)

        # Team-Tab Aenderungen verfolgen
        self.team_tab.plan = self.plan
        self.plan_tab.set_plan(self.plan)

        # Verbinde Aenderungen
        self.team_tab.plan = self.plan
        self.plan_tab.plan = self.plan

    def load_plan_to_ui(self):
        self.team_tab.set_plan(self.plan)
        self.plan_tab.set_plan(self.plan)
        self.window.mark_saved()

    def new_plan(self):
        if self.window.is_modified:
            reply = QMessageBox.question(
                self.window,
                "Nicht gespeichert",
                "Moechten Sie die Aenderungen speichern?",
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Save:
                self.save_plan()
            elif reply == QMessageBox.StandardButton.Cancel:
                return

        self.plan = self.create_new_plan()
        self.window.current_file_path = None
        self.load_plan_to_ui()

    def open_plan(self):
        path, _ = QFileDialog.getOpenFileName(
            self.window,
            "Plan oeffnen",
            filter="JSON-Dateien (*.json)"
        )
        if path:
            try:
                self.plan = load(path)
                self.window.current_file_path = path
                self.load_plan_to_ui()
                self.window.status_bar.showMessage(f"Geladen: {path}")
            except Exception as e:
                QMessageBox.critical(self.window, "Fehler", f"Laden fehlgeschlagen:\n{e}")

    def save_plan(self):
        if not self.window.current_file_path:
            path, _ = QFileDialog.getSaveFileName(
                self.window,
                "Plan speichern unter",
                filter="JSON-Dateien (*.json)"
            )
            if not path:
                return
            self.window.current_file_path = path

        try:
            self.plan.modified_at = datetime.now().isoformat()
            if not self.plan.created_at:
                self.plan.created_at = datetime.now().isoformat()
            save(self.plan, self.window.current_file_path)
            self.window.mark_saved()
            self.window.status_bar.showMessage(f"Gespeichert: {self.window.current_file_path}")
        except Exception as e:
            QMessageBox.critical(self.window, "Fehler", f"Speichern fehlgeschlagen:\n{e}")

    def export_csv(self):
        folder = QFileDialog.getExistingDirectory(self.window, "Zielordner waehlen")
        if folder:
            try:
                from export.csv_exporter import export_csv
                f1, f2 = export_csv(self.plan, folder)
                QMessageBox.information(
                    self.window,
                    "Erfolg",
                    f"CSV exportiert:\n{f1}\n{f2}"
                )
            except Exception as e:
                QMessageBox.critical(self.window, "Fehler", f"Export fehlgeschlagen:\n{e}")

    def export_excel(self):
        folder = QFileDialog.getExistingDirectory(self.window, "Zielordner waehlen")
        if folder:
            try:
                from export.excel_exporter import export_excel
                f = export_excel(self.plan, folder)
                QMessageBox.information(
                    self.window,
                    "Erfolg",
                    f"Excel exportiert:\n{f}"
                )
            except Exception as e:
                QMessageBox.critical(self.window, "Fehler", f"Export fehlgeschlagen:\n{e}")

    def export_pdf(self):
        folder = QFileDialog.getExistingDirectory(self.window, "Zielordner waehlen")
        if folder:
            try:
                from export.pdf_exporter import export_pdf
                f = export_pdf(self.plan, folder)
                QMessageBox.information(
                    self.window,
                    "Erfolg",
                    f"PDF exportiert:\n{f}"
                )
            except Exception as e:
                QMessageBox.critical(self.window, "Fehler", f"Export fehlgeschlagen:\n{e}")

    def run(self):
        self.window.show()
        return self.app.exec()


if __name__ == "__main__":
    app = JohannaApp()
    sys.exit(app.run())
