import signal
import sys
from datetime import datetime

from PySide6.QtWidgets import (
    QApplication, QMessageBox, QFileDialog, QProgressDialog, QInputDialog,
)
from PySide6.QtCore import QByteArray, QTimer, Qt
from PySide6.QtGui import QAction, QActionGroup

from version import __version__, GITHUB_REPO

from models import MonthPlan, month_label as month_label_safe
from persistence import (
    save, load, save_team, load_team, save_plan, load_plan,
    load_profiles, load_settings, save_settings,
    DataFileError, backup_path, pop_recoveries,
    backup_before_version_change, create_backup_zip,
)
from ui.main_window import MainWindow
from ui.team_tab import TeamTab
from ui.plan_tab import PlanTab
from ui.absence_tab import AbsenceTab
from ui import theme
from feedback import (
    ensure_month_folders, scan_new_files, read_file_text, parse_text,
    mark_processed, apply_feedback, month_folder, inbox_root,
    last_import, is_older_than_last, format_stamp,
)
from feedback.parser import KIND_LABELS


# Abstand zwischen zwei automatischen Sicherungen. Bewusst kurz: mehr als
# diese Zeitspanne an Arbeit soll ein Absturz nie kosten koennen
AUTOSAVE_INTERVAL_MS = 15_000


class JohannaApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.settings = load_settings()
        theme.apply_theme(
            self.app, self.settings.color_palette, self.settings.dark_mode
        )
        self.window = MainWindow()
        # Neue Programmversion (z. B. Ordner ueberschrieben): Daten sichern,
        # bevor sie im neuen Format gespeichert werden
        self._backup_on_version_change()
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
        # Urlaub/Wunsch/Soll im Raster geaendert: der Team-Tab zeigt nur
        # Vorlagen und Namen, ein Neuaufbau seiner Tabellen waere unnoetig
        self.plan_tab.constraints_changed.connect(self.absence_tab.refresh_all)
        # Ein Monat fuer alle Tabs: Monatswaehler in der Tab-Zeile
        self.window.month_selector.month_changed.connect(self.change_month)
        # Urlaub/Wunsch im eigenen Tab -> Dienstplan neu zeichnen
        self.absence_tab.absences_changed.connect(self.plan_tab.refresh_display)
        self.absence_tab.absences_changed.connect(self.window.mark_modified)
        # Tagesnotizen: Notizen-Reiter und Dienstplan-Dialog halten sich synchron
        self.absence_tab.notes_changed.connect(self.plan_tab.refresh_display)
        self.absence_tab.notes_changed.connect(self.window.mark_modified)
        self.plan_tab.notes_changed.connect(self.absence_tab.refresh_notes)
        self.absence_tab.notes_export_requested.connect(self.export_notes)
        self.absence_tab.month_change_requested.connect(self.change_month)
        self.plan_tab.import_requested.connect(self.import_feedback)
        self.window.on_close_request = self.handle_close_request

        self.load_plan_to_ui()
        self._restore_geometry()
        self._start_autosave()
        self._install_signal_handlers()
        self._report_recoveries()
        # Ablageordner: Monatsordner anlegen und neue Antworten ab dem
        # heutigen Monat einlesen - erst nach dem Fensteraufbau
        QTimer.singleShot(500, lambda: self.refresh_inbox(manual=False))

    def _backup_on_version_change(self):
        if self.settings.last_app_version == __version__:
            return
        try:
            target = backup_before_version_change(
                self.settings.last_app_version, __version__
            )
        except Exception as e:
            # Eine fehlgeschlagene Sicherung darf den Start nicht verhindern
            print(f"Datensicherung beim Versionswechsel fehlgeschlagen: {e}",
                  file=sys.stderr)
        else:
            if target is not None:
                self.window.status_bar.showMessage(
                    f"Neue Programmversion v{__version__}: Daten gesichert "
                    f"unter {target}", 10000
                )
        self.settings.last_app_version = __version__

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

        backup_action = QAction("Datensicherung erstellen...", self.window)
        backup_action.triggered.connect(self.create_data_backup)
        file_menu.addAction(backup_action)

        file_menu.addSeparator()
        import_action = QAction("Rueckmeldungen importieren...", self.window)
        import_action.setShortcut("Ctrl+I")
        import_action.triggered.connect(self.import_feedback)
        file_menu.addAction(import_action)

        inbox_action = QAction("Ablageordner aktualisieren", self.window)
        inbox_action.setToolTip(
            "Neue Antworten aus dem Ordner Formularantworten ab dem heutigen "
            "Monat einlesen und fehlende Monatsordner anlegen."
        )
        inbox_action.triggered.connect(lambda: self.refresh_inbox(manual=True))
        file_menu.addAction(inbox_action)
        file_menu.addSeparator()

        export_menu = file_menu.addMenu("Exportieren")
        for label, handler in [
            ("CSV", self.export_csv),
            ("Excel", self.export_excel),
            ("PDF", self.export_pdf),
            ("Notizen (Text)", self.export_notes),
            ("Rueckmeldeformular (HTML)...", self.export_form),
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
        self._setup_scheme_menu(settings_menu.addMenu("Farbschema"))

        update_action = QAction("Nach Updates suchen...", self.window)
        update_action.triggered.connect(self.check_updates_manual)
        settings_menu.addAction(update_action)

        # Hilfe: Anleitung und Planungslogik als HTML im Browser, Info-Dialog
        from ui.help import open_help, show_about
        from persistence.json_store import DATA_DIR
        help_menu = menubar.addMenu("Hilfe")
        manual_action = QAction("Bedienung...", self.window)
        manual_action.setShortcut("F1")
        manual_action.triggered.connect(lambda: open_help(self.window, "bedienung"))
        help_menu.addAction(manual_action)
        logic_action = QAction("Planungslogik...", self.window)
        logic_action.triggered.connect(lambda: open_help(self.window, "planungslogik"))
        help_menu.addAction(logic_action)
        help_menu.addSeparator()
        about_action = QAction("Info / Version...", self.window)
        about_action.triggered.connect(
            lambda: show_about(self.window, DATA_DIR, inbox_root())
        )
        help_menu.addAction(about_action)

    def _setup_scheme_menu(self, menu):
        """Einstellungen > Farbschema: vier Paletten, je hell und dunkel."""
        group = QActionGroup(self.window)
        group.setExclusive(True)
        for dark, heading in ((False, "Hell"), (True, "Dunkel")):
            menu.addSection(heading)
            for key, palette in theme.PALETTES.items():
                scheme = palette.dark if dark else palette.light
                action = QAction(theme.swatch_icon(scheme), palette.name, self.window)
                action.setCheckable(True)
                action.setChecked(
                    key == self.settings.color_palette
                    and dark == self.settings.dark_mode
                )
                action.triggered.connect(
                    lambda _checked=False, k=key, d=dark: self.set_color_scheme(k, d)
                )
                group.addAction(action)
                menu.addAction(action)

    def set_color_scheme(self, palette: str, dark: bool):
        """Farbschema sofort anwenden und dauerhaft merken."""
        self.settings.color_palette = palette
        self.settings.dark_mode = dark
        theme.apply_theme(self.app, palette, dark)
        # Fest eingefaerbte Tabellenzellen (Kopfzeilen, Kalender) neu aufbauen
        self.plan_tab.rebuild_grid()
        self.absence_tab.refresh_all()
        try:
            save_settings(self.settings)
        except Exception as e:
            self._report_save_error(e, "Speichern der Einstellungen")

    def load_plan_to_ui(self):
        self.team_tab.set_plan(self.plan)
        self.plan_tab.set_plan(self.plan)
        self.absence_tab.set_plan(self.plan)
        self.window.month_selector.set_month(self.plan.year, self.plan.month)
        self.window.set_title_plan(self.plan.year, self.plan.month)
        self.window.mark_saved()

    def change_month(self, year: int, month: int):
        """Monatswechsel fuer alle Tabs: aktuellen Monat speichern,
        Zielmonat laden. Schlaegt etwas fehl, zeigt der Monatswaehler
        wieder den weiter geoeffneten Monat."""
        try:
            self._change_month(year, month)
        finally:
            self.window.month_selector.set_month(self.plan.year, self.plan.month)

    def _change_month(self, year: int, month: int):
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

    def create_data_backup(self):
        """Datei > Datensicherung erstellen: aktuellen Stand speichern und den
        ganzen data-Ordner als ZIP an einen frei gewaehlten Ort legen."""
        folder = QFileDialog.getExistingDirectory(
            self.window, "Zielordner fuer die Datensicherung waehlen"
        )
        if not folder:
            return
        if not self._save_current_guarded(context="Speichern vor der Datensicherung"):
            return
        try:
            path = create_backup_zip(folder)
        except Exception as e:
            self._report_save_error(e, "Datensicherung", force_dialog=True)
            return
        QMessageBox.information(
            self.window, "Datensicherung",
            f"Alle Daten (Team, Plaene, Einstellungen) gesichert:\n{path}\n\n"
            "Zurueckholen: Programm schliessen und den Ordner \"data\" aus "
            "dem ZIP in den Programmordner kopieren.",
        )

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
                # Das PDF uebernimmt die Eintragsfarben aus den Einstellungen
                f = export_pdf(self.plan, folder, self.settings)
                QMessageBox.information(self.window, "Erfolg", f"PDF exportiert:\n{f}")
            except Exception as e:
                QMessageBox.critical(self.window, "Fehler", f"Export fehlgeschlagen:\n{e}")

    def export_notes(self):
        """Alle Tagesnotizen des Monats gesammelt als Textdatei."""
        folder = QFileDialog.getExistingDirectory(self.window, "Zielordner waehlen")
        if folder:
            try:
                from export.notes_exporter import export_notes
                f = export_notes(self.plan, folder)
                QMessageBox.information(self.window, "Erfolg", f"Notizen exportiert:\n{f}")
            except Exception as e:
                QMessageBox.critical(self.window, "Fehler", f"Export fehlgeschlagen:\n{e}")

    def export_form(self):
        """Rueckmeldeformular fuer den geoeffneten Monat mit den aktuellen
        Helfern erzeugen. Die Datei wird von Hand verschickt (Anhang im
        Webmailer) - deshalb nur Empfaenger abfragen und Datei ablegen."""
        from export.form_exporter import export_form
        from models import month_label
        label = month_label(self.plan.year, self.plan.month)
        recipient, ok = QInputDialog.getText(
            self.window, "Rueckmeldeformular",
            f"Formular fuer {label} mit {len(self.plan.assistants)} Helfern.\n\n"
            "E-Mail-Adresse, an die die Helfer ihre Rueckmeldung schicken\n"
            "(wird im Formular eingetragen; leer = Helfer tragen sie selbst ein):",
            text=self.settings.form_recipient,
        )
        if not ok:
            return
        if recipient.strip() != self.settings.form_recipient:
            self.settings.form_recipient = recipient.strip()
            self.window.mark_modified()
        # Ablageordner dieses Monats (und der naechsten) anlegen; er ist der
        # vorgeschlagene Zielordner, dort landen spaeter auch die Antworten
        try:
            ensure_month_folders(self.plan.year, self.plan.month)
            suggested = str(month_folder(self.plan.year, self.plan.month))
        except OSError as e:
            print(f"Ablageordner nicht angelegt: {e}", file=sys.stderr)
            suggested = ""
        folder = QFileDialog.getExistingDirectory(
            self.window, "Zielordner waehlen", suggested
        )
        if not folder:
            return
        try:
            f = export_form(self.plan, folder, recipient)
        except Exception as e:
            QMessageBox.critical(self.window, "Fehler", f"Export fehlgeschlagen:\n{e}")
            return
        QMessageBox.information(
            self.window, "Rueckmeldeformular",
            f"Formular erzeugt:\n{f}\n\n"
            "Die Datei als Anhang an alle Helfer schicken (z. B. im Webmailer). "
            "Jeder oeffnet sie im Browser, tippt seine Tage an und schickt den "
            "fertigen Text per E-Mail zurueck.\n\n"
            f"Antworten dann im Ablageordner {inbox_root()} in den Monatsordner "
            "legen - sie werden beim naechsten Start eingelesen - oder ueber "
            "\"Import\" einfuegen.",
        )

    # --- Rueckmeldungen der Helfer ---------------------------------------

    def import_feedback(self, initial_files=None):
        """Datei > Rueckmeldungen importieren / Import-Button: Dialog mit
        Vorschau; erst "Uebernehmen" traegt ein."""
        from ui.import_dialog import ImportDialog
        dialog = ImportDialog(self.plan, self.window, initial_files=initial_files)
        if not dialog.exec():
            return
        self.apply_feedback_list(dialog.feedbacks(), show_summary=True)

    def apply_feedback_list(self, feedbacks, show_summary: bool) -> list[str]:
        """Traegt gueltige Rueckmeldungen ein, merkt eingelesene Dateien im
        Ablageordner und aktualisiert alle Tabs. Gibt die Protokollzeilen
        zurueck."""
        by_id = {a.id: a for a in self.plan.assistants}
        lines = []
        # Aelteste zuerst: liegen mehrere Rueckmeldungen desselben Helfers fuer
        # denselben Monat vor, gilt am Ende die neueste
        for fb in sorted(feedbacks, key=lambda f: (f.month_key(), f.assistant_id, f.stamp)):
            assistant = by_id.get(fb.assistant_id)
            if assistant is None or not fb.ok:
                continue
            if is_older_than_last(assistant, fb) and not self._confirm_older(assistant, fb):
                lines.append(
                    f"{assistant.name}, {fb.month_key()}: aelterer Stand "
                    f"({format_stamp(fb.stamp)}) nicht uebernommen"
                )
                if fb.path is not None:
                    try:
                        mark_processed(fb.path, lines[-1])
                    except OSError:
                        pass
                continue
            apply_feedback(assistant, fb)
            counts = ", ".join(
                f"{fb.count(k)} {KIND_LABELS[k]}" for k in KIND_LABELS if fb.count(k)
            ) or "keine Tage"
            summary = f"{assistant.name}, {fb.month_key()}: {counts}"
            summary += f" (Stand {format_stamp(fb.stamp) or 'ohne Zeitstempel'})"
            if fb.note:
                summary += f"; Bemerkung: {fb.note}"
            lines.append(summary)
            if fb.path is not None:
                try:
                    mark_processed(fb.path, summary)
                except OSError as e:
                    print(f"Eingelesen-Merker nicht geschrieben: {e}", file=sys.stderr)
        if lines:
            self.plan_tab.refresh_display()
            self.absence_tab.refresh_all()
            self.window.mark_modified()
            self.window.status_bar.showMessage(
                f"{len(lines)} Rueckmeldung(en) uebernommen", 8000
            )
            if show_summary:
                QMessageBox.information(
                    self.window, "Rueckmeldungen uebernommen", "\n".join(lines)
                )
        return lines

    def _confirm_older(self, assistant, fb) -> bool:
        """Rueckfrage: die Rueckmeldung ist aelter als die zuletzt eingelesene."""
        last = last_import(assistant, fb.year, fb.month) or {}
        reply = QMessageBox.question(
            self.window, "Aeltere Rueckmeldung",
            f"{assistant.name}, {month_label_safe(fb.year, fb.month)}:\n\n"
            f"Diese Rueckmeldung hat den Stand {format_stamp(fb.stamp)}.\n"
            f"Zuletzt eingelesen wurde ein neuerer Stand vom "
            f"{format_stamp(last.get('stand', ''))} "
            f"(eingelesen am {format_stamp(last.get('eingelesen', ''))}).\n\n"
            "Die aeltere Rueckmeldung trotzdem uebernehmen? Sie ersetzt dann "
            "den neueren Stand.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    def refresh_inbox(self, manual: bool):
        """Programmstart / Datei > Ablageordner aktualisieren: Monatsordner
        ab heute anlegen, neue Antworten ab dem heutigen Monat einlesen."""
        today = datetime.now()
        try:
            ensure_month_folders(today.year, today.month)
            files = scan_new_files(min_month=(today.year, today.month))
        except OSError as e:
            self._report_save_error(e, "Ablageordner", force_dialog=manual)
            return
        feedbacks, problems = [], []
        for path in files:
            try:
                found = parse_text(read_file_text(path), source=path.name)
            except Exception as e:
                problems.append(f"{path.name}: nicht lesbar ({e})")
                continue
            if not found:
                problems.append(f"{path.name}: keine Rueckmeldung (JA1-Zeile) gefunden")
                continue
            for fb in found:
                fb.path = path
                if fb.ok and fb.assistant_id not in {a.id for a in self.plan.assistants}:
                    fb.error = "Helfer-ID unbekannt"
                if fb.ok:
                    feedbacks.append(fb)
                else:
                    problems.append(f"{path.name}: {fb.error}")
        lines = self.apply_feedback_list(feedbacks, show_summary=False)
        if not lines and not problems:
            if manual:
                QMessageBox.information(
                    self.window, "Ablageordner",
                    f"Keine neuen Rueckmeldungen in\n{inbox_root()}",
                )
            return
        text = ""
        if lines:
            text += "Eingelesen:\n" + "\n".join(lines)
        if problems:
            text += ("\n\n" if text else "") + "Nicht uebernommen:\n" + "\n".join(problems)
        QMessageBox.information(self.window, "Ablageordner aktualisiert", text)

    # --- Automatisches Update (GitHub-Releases) -------------------------

    def _check_updates_startup(self):
        """Stiller Start-Check: meldet sich nur, wenn es ein Update gibt.

        Nur die installierte (gefrorene) Windows-Version kann sich selbst
        aktualisieren - im Entwicklungsmodus passiert beim Start nichts."""
        if not (getattr(sys, "frozen", False) and sys.platform == "win32"):
            return
        self._start_update_check(manual=False)

    def check_updates_manual(self):
        """Einstellungen > Nach Updates suchen: meldet jedes Ergebnis."""
        self._start_update_check(manual=True)

    def _start_update_check(self, manual: bool):
        from updater import UpdateChecker
        checker = getattr(self, "_update_checker", None)
        if checker is not None and checker.isRunning():
            return
        self._update_checker = UpdateChecker(self.window)
        self._update_checker.result.connect(
            lambda release, m=manual: self._on_update_check_done(release, m)
        )
        self._update_checker.start()

    def _on_update_check_done(self, release, manual: bool):
        from updater import is_newer
        if release is None:
            # Kein Release, Rate-Limit oder kein Internet - beim Start still
            if manual:
                QMessageBox.warning(
                    self.window, "Updates",
                    "Die Update-Pruefung ist fehlgeschlagen.\n"
                    "Bitte Internetverbindung pruefen und spaeter erneut "
                    "versuchen.",
                )
            return
        if not is_newer(release["tag"], __version__):
            if manual:
                QMessageBox.information(
                    self.window, "Updates",
                    f"Sie verwenden bereits die neueste Version "
                    f"(v{__version__}).",
                )
            return
        if not manual and release["tag"] == self.settings.skipped_version:
            return
        if not (getattr(sys, "frozen", False) and sys.platform == "win32"):
            # Manueller Check aus der Entwicklungsumgebung heraus
            QMessageBox.information(
                self.window, "Update verfuegbar",
                f"Version {release['tag']} ist verfuegbar. Die automatische "
                "Installation gibt es nur in der installierten "
                "Windows-Version.\n"
                f"Download: https://github.com/{GITHUB_REPO}/releases",
            )
            return
        self._offer_update(release, manual)

    def _offer_update(self, release: dict, manual: bool):
        box = QMessageBox(self.window)
        box.setWindowTitle("Update verfuegbar")
        box.setIcon(QMessageBox.Icon.Question)
        box.setText(
            "Eine neue Version von Johanna Assistenten ist verfuegbar.\n\n"
            f"Installiert: v{__version__}\n"
            f"Neu: {release['tag']}\n\n"
            "Jetzt herunterladen und installieren?\n"
            "Das Programm wird dazu neu gestartet. Ihre Daten (Ordner data) "
            "bleiben erhalten."
        )
        install_btn = box.addButton(
            "Jetzt installieren", QMessageBox.ButtonRole.AcceptRole
        )
        box.addButton("Spaeter", QMessageBox.ButtonRole.RejectRole)
        skip_btn = None
        if not manual:
            skip_btn = box.addButton(
                "Diese Version ueberspringen",
                QMessageBox.ButtonRole.DestructiveRole,
            )
        box.exec()
        clicked = box.clickedButton()
        if clicked is install_btn:
            self._install_update(release)
        elif skip_btn is not None and clicked is skip_btn:
            self.settings.skipped_version = release["tag"]
            try:
                save_settings(self.settings)
            except Exception as e:
                self._report_save_error(e, "Speichern der Einstellungen")

    def _install_update(self, release: dict):
        from updater import UpdateDownloader
        # Nie mit ungesicherten Aenderungen updaten
        if not self._save_current_guarded(context="Speichern vor dem Update"):
            return

        dialog = QProgressDialog(
            "Update wird heruntergeladen...", "Abbrechen", 0, 100, self.window
        )
        dialog.setWindowTitle("Update")
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.setMinimumDuration(0)
        dialog.setAutoClose(False)
        dialog.setAutoReset(False)

        downloader = UpdateDownloader(release["zip_url"], self.window)
        self._update_downloader = downloader

        def on_progress(received: int, total: int):
            if total > 0:
                dialog.setMaximum(100)
                dialog.setValue(min(100, received * 100 // total))
            else:
                dialog.setMaximum(0)  # unbekannte Groesse: Laufbalken

        def on_ok(new_dir):
            dialog.close()
            self._apply_update(new_dir)

        def on_failed(message: str):
            dialog.close()
            self._report_update_failure(message)

        downloader.progress.connect(on_progress)
        downloader.finished_ok.connect(on_ok)
        downloader.failed.connect(on_failed)
        dialog.canceled.connect(downloader.cancel)
        downloader.start()
        dialog.exec()

    def _apply_update(self, new_dir):
        from pathlib import Path
        from updater import launch_swap_and_restart
        try:
            launch_swap_and_restart(Path(new_dir), Path(sys.executable).parent)
        except Exception as e:
            self._report_update_failure(str(e))
            return
        # Alles ist gespeichert; das Tausch-Skript wartet auf das
        # Programmende und startet dann die neue Version
        self._autosave_timer.stop()
        self.window.on_close_request = None
        self.app.quit()

    def _report_update_failure(self, message: str):
        QMessageBox.critical(
            self.window, "Update fehlgeschlagen",
            f"Das Update konnte nicht installiert werden:\n\n{message}\n\n"
            "Das Programm laeuft unveraendert weiter. Sie koennen das "
            "Update auch manuell von GitHub herunterladen:\n"
            f"https://github.com/{GITHUB_REPO}/releases",
        )

    def run(self):
        self.window.show()
        # Update-Check erst nach dem Fensteraufbau, ohne das UI zu blockieren
        QTimer.singleShot(2000, self._check_updates_startup)
        return self.app.exec()


if __name__ == "__main__":
    app = JohannaApp()
    sys.exit(app.run())
