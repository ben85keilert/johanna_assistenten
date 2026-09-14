import signal
import sys
from datetime import datetime

from PySide6.QtWidgets import QApplication, QMessageBox, QFileDialog
from PySide6.QtCore import QByteArray, QTimer
from PySide6.QtGui import QAction

from models import MonthPlan
from persistence import (
    save, load, save_team, load_team, save_plan, load_plan,
    load_profiles, load_settings, save_settings,
    DataFileError, backup_path, pop_recoveries,
)
from ui.main_window import MainWindow
from ui.team_tab import TeamTab
from ui.plan_tab import PlanTab
from ui.absence_tab import AbsenceTab
from ui.theme import apply_theme


# Abstand zwischen zwei automatischen Sicherungen. Bewusst kurz: mehr als
# diese Zeitspanne an Arbeit soll ein Absturz nie kosten koennen
AUTOSAVE_INTERVAL_MS = 15_000


class JohannaApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        apply_theme(self.app)
        self.settings = load_settings()
        self.window = MainWindow()
        # Plan + die zwei monatsuebergreifenden Einstellungs-Vorlagen
        self.plan, self.profiles = self._auto_load()
        # Ein Speicherfehler (schreibgeschuetzter Ordner, volle Platte) wird
        # nur einmal als Dialog gezeigt - sonst alle 15 Sekunden erneut
        self._save_error_shown = False

        self.team_tab = TeamTab()
        self.team_tab.set_profiles(self.profiles)
        self.plan_tab = PlanTab(self.settings)
        self.absence_tab = AbsenceTab(self.settings)

        self.window.set_plan_tab(self.plan_tab)
        self.window.set_absence_tab(self.absence_tab)
        self.window.set_team_tab(self.team_tab)

        self.setup_menu()

        # Signale verdrahten: Aenderungen sofort in allen Tabs sichtbar
        self.team_tab.assistants_changed.connect(self.plan_tab.rebuild_grid)
        self.team_tab.assistants_changed.connect(self.absence_tab.refresh_all)
        self.team_tab.assistants_changed.connect(self.window.mark_modified)
        self.team_tab.profiles_changed.connect(self.window.mark_modified)
        self.plan_tab.plan_modified.connect(self.window.mark_modified)
        self.plan_tab.constraints_changed.connect(self.team_tab.refresh_all)
        self.plan_tab.constraints_changed.connect(self.absence_tab.refresh_all)
        self.plan_tab.month_change_requested.connect(self.change_month)
        # Urlaub/Block im eigenen Tab -> Dienstplan neu zeichnen
        self.absence_tab.absences_changed.connect(self.plan_tab.refresh_display)
        self.absence_tab.absences_changed.connect(self.window.mark_modified)
        self.window.on_close_request = self.handle_close_request

        self.load_plan_to_ui()
        self._restore_geometry()
        self._start_autosave()
        self._install_signal_handlers()
        self._report_recoveries()

    def _auto_load(self) -> tuple[MonthPlan, list]:
        # Letzten Zustand wiederherstellen: zuletzt geoeffneter Monat,
        # sonst der aktuelle Kalendermonat
        now = datetime.now()
        year = self.settings.last_year or now.year
        month = self.settings.last_month or now.month

        try:
            assistants = load_team()
            plan = load_plan(year, month, assistants)
            profiles = load_profiles()
        except DataFileError as e:
            self._abort_on_broken_file(e)

        if plan is None:
            plan = MonthPlan(year=year, month=month, assistants=assistants)
        return plan, profiles

    def _abort_on_broken_file(self, error: DataFileError):
        """Beschaedigte Datendatei: lieber gar nicht starten.

        Mit leeren Daten weiterzuarbeiten wuerde die kaputte Datei beim
        naechsten automatischen Speichern endgueltig ueberschreiben.
        """
        QMessageBox.critical(
            self.window,
            "Datei beschaedigt",
            f"Die Datei\n{error.path}\nkonnte nicht gelesen werden:\n\n"
            f"{error.reason}\n\n"
            "Das Programm wird beendet, damit die Datei nicht ueberschrieben "
            "wird. Eine aeltere Fassung liegt gegebenenfalls unter\n"
            f"{backup_path(error.path)}",
        )
        sys.exit(1)

    def _report_recoveries(self):
        """Hinweis, wenn eine Datei aus ihrer Sicherungskopie kam."""
        notes = pop_recoveries()
        if notes:
            QMessageBox.warning(
                self.window,
                "Aus Sicherungskopie wiederhergestellt",
                "\n\n".join(notes)
                + "\n\nBitte pruefen, ob der angezeigte Stand vollstaendig ist.",
            )

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

        save_as_action = QAction("Speichern unter...", self.window)
        save_as_action.setShortcut("Ctrl+Shift+S")
        save_as_action.triggered.connect(self.save_plan_as)
        file_menu.addAction(save_as_action)

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

        settings_menu = menubar.addMenu("Einstellungen")
        colors_action = QAction("Farben...", self.window)
        colors_action.triggered.connect(self.open_color_settings)
        settings_menu.addAction(colors_action)

    def load_plan_to_ui(self):
        self.team_tab.set_plan(self.plan)
        self.plan_tab.set_plan(self.plan)
        self.absence_tab.set_plan(self.plan)
        self.window.set_title_plan(self.plan.year, self.plan.month)
        self.window.mark_saved()

    def change_month(self, year: int, month: int):
        """Monatswechsel: aktuellen Monat speichern, Zielmonat laden."""
        if (year, month) == (self.plan.year, self.plan.month):
            return

        if not self._save_current_guarded():
            return

        try:
            assistants = load_team()
            plan = load_plan(year, month, assistants)
        except DataFileError as e:
            QMessageBox.critical(
                self.window,
                "Fehler",
                f"Monat {year}-{month:02d} konnte nicht geladen werden:\n\n{e}",
            )
            return
        self._report_recoveries()
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
        if not path:
            return

        # Die Datei bringt ein eigenes Team mit. Beim naechsten (automatischen)
        # Speichern ersetzt es data/team.json samt Abwesenheiten - das muss
        # der Nutzer wissen, bevor es 15 Sekunden spaeter still passiert
        reply = QMessageBox.question(
            self.window,
            "Plan-Datei oeffnen",
            f"{path}\n\n"
            "Die Datei ersetzt Team und Monatsplan der laufenden Sitzung.\n"
            "Beim naechsten Speichern werden data/team.json und der Monatsplan "
            "damit ueberschrieben.\n\nFortfahren?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if not self._save_current_guarded():
            return

        try:
            self.plan = load(path)
        except Exception as e:
            QMessageBox.critical(self.window, "Fehler", f"Laden fehlgeschlagen:\n{e}")
            return
        self._report_recoveries()
        self.settings.last_year = self.plan.year
        self.settings.last_month = self.plan.month
        self.load_plan_to_ui()
        self.window.status_bar.showMessage(f"Geladen: {path}")

    def _save_current(self, update_status: bool = True):
        """Schreibt Team + Monatsplan + App-Einstellungen.

        Wirft bei Schreibfehlern - Aufrufer nutzen ueblicherweise
        _save_current_guarded(), das den Fehler dem Nutzer meldet.
        """
        self.plan.modified_at = datetime.now().isoformat()
        if not self.plan.created_at:
            self.plan.created_at = datetime.now().isoformat()
        save_team(self.plan.assistants, self.profiles)
        save_plan(self.plan)
        self._save_settings()
        self.window.mark_saved()
        if update_status:
            self.window.status_bar.showMessage(
                f"Gespeichert: Plan {self.plan.year}-{self.plan.month:02d}"
            )

    def _save_current_guarded(self, update_status: bool = False,
                              context: str = "Speichern") -> bool:
        """Speichert und meldet Fehler. True = alles auf der Platte."""
        try:
            self._save_current(update_status=update_status)
        except Exception as e:
            self._report_save_error(e, context)
            return False
        self._save_error_shown = False
        return True

    def save_all(self):
        self._save_current_guarded(update_status=True)

    def save_plan_as(self):
        """Speichert den aktuellen Plan als frei benannte Datei (Kopie).

        Die Datei enthaelt den vollstaendigen Plan samt Team und laesst sich
        ueber "Plan-Datei oeffnen..." wieder laden. Die normale Ablage unter
        data/plans/ laeuft davon unabhaengig weiter.
        """
        suggested = f"plan_{self.plan.year}_{self.plan.month:02d}.json"
        path, _ = QFileDialog.getSaveFileName(
            self.window, "Plan speichern unter", suggested,
            "JSON-Dateien (*.json)",
        )
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        try:
            save(self.plan, path)
        except Exception as e:
            self._report_save_error(e, "Speichern unter", force_dialog=True)
            return
        self.window.status_bar.showMessage(f"Gespeichert unter: {path}")

    def open_color_settings(self):
        """Einstellungen > Farben: Farbe je Eintragsart aendern."""
        from ui.color_settings_dialog import ColorSettingsDialog
        dialog = ColorSettingsDialog(self.settings, self.window)
        if not dialog.exec():
            return
        # Sofort anwenden und die Auswahl dauerhaft merken
        self.plan_tab.refresh_display()
        self.absence_tab.refresh_calendar()
        try:
            save_settings(self.settings)
        except Exception as e:
            self._report_save_error(e, "Speichern der Einstellungen")

    def _save_settings(self):
        self.settings.last_year = self.plan.year
        self.settings.last_month = self.plan.month
        self.settings.window_geometry = bytes(
            self.window.saveGeometry().toHex()
        ).decode()
        save_settings(self.settings)

    def _report_save_error(self, error: Exception, context: str,
                           force_dialog: bool = False):
        # Immer sichtbar in der Statuszeile; der Dialog nur einmal pro
        # Sitzung, damit ein dauerhaft schreibgeschuetzter Ordner nicht alle
        # 15 Sekunden ein Fenster oeffnet
        text = f"{context} fehlgeschlagen: {error}"
        self.window.status_bar.showMessage(text)
        print(text, file=sys.stderr)
        if force_dialog or not self._save_error_shown:
            self._save_error_shown = True
            QMessageBox.critical(
                self.window,
                "Speichern fehlgeschlagen",
                f"{context} fehlgeschlagen:\n\n{error}\n\n"
                "Die Aenderungen stehen noch nicht auf der Festplatte.\n"
                "Bitte Schreibrechte und freien Speicherplatz pruefen.",
            )

    # --- Automatisches Speichern ---------------------------------------

    def _start_autosave(self):
        """Sichert alle AUTOSAVE_INTERVAL_MS, sofern es Aenderungen gibt.

        Damit kostet ein Absturz oder Stromausfall hoechstens die Arbeit
        der letzten Sekunden statt der ganzen Sitzung.
        """
        self._autosave_timer = QTimer(self.window)
        self._autosave_timer.setInterval(AUTOSAVE_INTERVAL_MS)
        self._autosave_timer.timeout.connect(self._autosave_tick)
        self._autosave_timer.start()

    def _autosave_tick(self):
        if not self.window.is_modified:
            return
        if self._save_current_guarded(context="Automatisches Speichern"):
            self.window.status_bar.showMessage(
                f"Automatisch gespeichert ({datetime.now():%H:%M:%S})", 5000
            )

    def _install_signal_handlers(self):
        """Rettet die Daten bei SIGTERM/SIGINT (Abmelden, Herunterfahren,
        Strg+C im Terminal). Ein hartes Abschiessen (Task-Manager, Stromaus)
        laesst sich nicht abfangen - dagegen hilft nur der Autosave-Timer."""
        def handler(signum, _frame):
            try:
                self._save_current(update_status=False)
            except Exception as e:
                print(f"Speichern beim Abbruch fehlgeschlagen: {e}", file=sys.stderr)
            self.app.quit()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, handler)
            except (ValueError, OSError, AttributeError):
                # Nicht jeder Plattform/Thread erlaubt das - dann eben nicht
                pass

        # Python-Signalhandler laufen nur, wenn der Interpreter an der Reihe
        # ist; die Qt-Event-Loop wartet sonst in C++. Dieser Leerlauf-Timer
        # gibt ihm regelmaessig kurz die Gelegenheit dazu.
        self._signal_pump = QTimer(self.window)
        self._signal_pump.setInterval(300)
        self._signal_pump.timeout.connect(lambda: None)
        self._signal_pump.start()

    # --- Beenden --------------------------------------------------------

    def handle_close_request(self) -> bool:
        """Vor dem Schliessen: nachfragen, wenn seit dem letzten
        automatischen Speichern noch Aenderungen offen sind.
        Rueckgabe False = Fenster bleibt offen."""
        if self.window.is_modified:
            choice = self._ask_unsaved_on_close()
            if choice == "cancel":
                return False
            if choice == "discard":
                # Plandaten bewusst nicht schreiben; nur Fenstergroesse und
                # zuletzt geoeffneter Monat werden gemerkt
                try:
                    self._save_settings()
                except Exception as e:
                    print(f"Einstellungen nicht gespeichert: {e}", file=sys.stderr)
                return True

        try:
            self._save_current(update_status=False)
        except Exception as e:
            self._report_save_error(e, "Speichern beim Beenden", force_dialog=True)
            return self._ask_close_anyway()
        return True

    def _ask_unsaved_on_close(self) -> str:
        box = QMessageBox(self.window)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Beenden")
        box.setText("Es gibt Aenderungen, die noch nicht gespeichert sind.")
        box.setInformativeText("Vor dem Beenden speichern?")
        save_button = box.addButton(
            "Speichern und beenden", QMessageBox.ButtonRole.AcceptRole
        )
        discard_button = box.addButton(
            "Ohne Speichern beenden", QMessageBox.ButtonRole.DestructiveRole
        )
        box.addButton("Abbrechen", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(save_button)
        box.exec()

        clicked = box.clickedButton()
        if clicked is save_button:
            return "save"
        if clicked is discard_button:
            return "discard"
        return "cancel"

    def _ask_close_anyway(self) -> bool:
        box = QMessageBox(self.window)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Beenden")
        box.setText("Die Aenderungen konnten nicht gespeichert werden.")
        box.setInformativeText("Trotzdem beenden? Die Aenderungen gehen verloren.")
        close_button = box.addButton(
            "Trotzdem beenden", QMessageBox.ButtonRole.DestructiveRole
        )
        back_button = box.addButton("Zurueck zum Plan", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(back_button)
        box.exec()
        return box.clickedButton() is close_button

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
