from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QMessageBox, QHeaderView, QTabWidget,
    QGroupBox, QListWidget, QListWidgetItem, QDialog, QComboBox,
    QDateEdit, QLabel
)
from PySide6.QtCore import Qt, Signal, QDate
from PySide6.QtGui import QColor, QPixmap

from models import (
    Assistant, AssistantConstraints, MonthPlan,
    AssistantSettings, SettingsProfile, apply_settings,
    absence_days, set_absence_days, blocked_days, set_blocked_days,
)
from persistence import default_profiles
from datetime import date, timedelta
import calendar
import uuid

from . import theme
from .widgets.color_button import ColorButton
from .widgets.big_stepper import BigStepper

# Auswahl fuer "RB anhaengen": Rufbereitschafts-Block direkt vor/nach dem
# Dienstblock (fuer Helfer mit weiter Anreise, die am Stueck bleiben wollen)
ATTACH_OPTIONS = [("—", "none"), ("Vorher", "before"), ("Nachher", "after")]


class TeamTab(QWidget):
    # Helferliste/Abwesenheiten oder Plan-Einstellungen geaendert
    assistants_changed = Signal()
    # Eine Vorlage wurde geaendert (wird beim Speichern mitgesichert)
    profiles_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.plan: MonthPlan | None = None
        self.profiles: list[SettingsProfile] = default_profiles()
        self._steppers = {}  # (profile_idx, assistant_id, field) -> BigStepper
        self._refreshing = False
        self.init_ui()

    def _init_filter_bar(self):
        """Filter fuer die Abwesenheitsliste; sitzt in der Tab-Zeile
        (Corner-Widget), sichtbar solange der Team-Tab aktiv ist."""
        self.top_bar = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 8, 0)

        layout.addWidget(QLabel("Abwesenheiten:"))
        self.filter_person_combo = QComboBox()
        self.filter_person_combo.currentIndexChanged.connect(self.refresh_vacations)
        layout.addWidget(self.filter_person_combo)

        self.filter_month_combo = QComboBox()
        self.filter_month_combo.currentIndexChanged.connect(self.refresh_vacations)
        layout.addWidget(self.filter_month_combo)

        self.show_past_btn = QPushButton("Vergangene anzeigen")
        self.show_past_btn.setCheckable(True)
        self.show_past_btn.setToolTip(
            "Bereits abgelaufene Abwesenheiten ein-/ausblenden"
        )
        self.show_past_btn.toggled.connect(self.refresh_vacations)
        layout.addWidget(self.show_past_btn)

        self.top_bar.setLayout(layout)

    def init_ui(self):
        self._init_filter_bar()
        layout = QHBoxLayout()

        # Linke Seite: Helfer-Buttons + zwei Einstellungs-Vorlagen als Tabs
        left_layout = QVBoxLayout()
        button_layout = QHBoxLayout()
        self.add_btn = QPushButton("+ Helfer hinzufuegen")
        self.add_btn.clicked.connect(self.add_assistant)
        button_layout.addWidget(self.add_btn)

        self.remove_btn = QPushButton("- Entfernen")
        self.remove_btn.clicked.connect(self.remove_assistant)
        button_layout.addWidget(self.remove_btn)

        button_layout.addStretch()
        left_layout.addLayout(button_layout)

        # Zwei Vorlagen: Einstellungen getrennt vorbereiten und per Button
        # in den Dienstplan des aktuellen Monats uebernehmen
        self.profile_tabs = QTabWidget()
        self._tables: list[QTableWidget] = []
        self._apply_buttons: list[QPushButton] = []
        for idx in range(2):
            page = QWidget()
            page_layout = QVBoxLayout()

            table = QTableWidget()
            table.setColumnCount(8)
            table.setHorizontalHeaderLabels([
                "Farbe", "Name", "Min. Dienste", "Max. Dienste",
                "Max. Folge", "Min. Block", "Abstand", "RB anhaengen",
            ])
            table.itemChanged.connect(
                lambda item, i=idx: self.on_name_edited(i, item)
            )
            page_layout.addWidget(table)

            apply_layout = QHBoxLayout()
            apply_btn = QPushButton("In Dienstplan uebernehmen")
            apply_btn.setToolTip(
                "Uebertraegt die Einstellungen dieser Vorlage in den "
                "Dienstplan des aktuell geoeffneten Monats."
            )
            apply_btn.clicked.connect(lambda _, i=idx: self.apply_profile(i))
            apply_layout.addWidget(apply_btn)
            apply_layout.addStretch()
            page_layout.addLayout(apply_layout)

            page.setLayout(page_layout)
            self.profile_tabs.addTab(page, f"Vorlage {idx + 1}")
            self._tables.append(table)
            self._apply_buttons.append(apply_btn)

        left_layout.addWidget(self.profile_tabs)
        layout.addLayout(left_layout, stretch=3)

        # Rechte Seite: Abwesenheitsuebersicht, chronologisch sortiert
        vacation_group = QGroupBox("Abwesenheiten (chronologisch)")
        vacation_layout = QVBoxLayout()
        self.vacation_list = QListWidget()
        self.vacation_list.itemDoubleClicked.connect(lambda _: self.edit_vacation())
        vacation_layout.addWidget(self.vacation_list)

        vacation_buttons = QHBoxLayout()
        self.vacation_add_btn = QPushButton("+ Abwesenheit hinzufuegen")
        self.vacation_add_btn.clicked.connect(self.add_vacation)
        vacation_buttons.addWidget(self.vacation_add_btn)
        self.vacation_edit_btn = QPushButton("Bearbeiten")
        self.vacation_edit_btn.clicked.connect(self.edit_vacation)
        vacation_buttons.addWidget(self.vacation_edit_btn)
        self.vacation_remove_btn = QPushButton("- Entfernen")
        self.vacation_remove_btn.clicked.connect(self.remove_vacation)
        vacation_buttons.addWidget(self.vacation_remove_btn)
        vacation_buttons.addStretch()
        vacation_layout.addLayout(vacation_buttons)

        vacation_group.setLayout(vacation_layout)
        layout.addWidget(vacation_group, stretch=2)

        self.setLayout(layout)

    def set_plan(self, plan: MonthPlan):
        self.plan = plan
        self.refresh_table()
        self.refresh_vacations()

    def set_profiles(self, profiles: list[SettingsProfile]):
        self.profiles = profiles
        self.refresh_table()

    def refresh_all(self):
        """Von aussen aufrufen, wenn Einschraenkungen anderswo geaendert wurden."""
        self.refresh_table()
        self.refresh_vacations()

    # --- Vorlagen-Tabellen ---

    def _profile_settings(self, profile_idx: int, assistant_id: str) -> AssistantSettings:
        return self.profiles[profile_idx].settings.setdefault(
            assistant_id, AssistantSettings()
        )

    def _make_stepper(self, profile_idx: int, assistant, field: str, label: str,
                      value: int, minimum: int, maximum: int,
                      special_min_text: str | None = None) -> BigStepper:
        stepper = BigStepper(
            label=f"{assistant.name}: {label}",
            value=value, minimum=minimum, maximum=maximum,
            special_min_text=special_min_text,
        )
        stepper.value_changed.connect(
            lambda v, p=profile_idx, aid=assistant.id, f=field:
            self.on_stepper_changed(p, aid, f, v)
        )
        self._steppers[(profile_idx, assistant.id, field)] = stepper
        return stepper

    def on_stepper_changed(self, profile_idx: int, assistant_id: str,
                           field: str, value: int):
        s = self._profile_settings(profile_idx, assistant_id)

        if field == "min_target":
            s.min_shifts = None if value < 0 else value
            # Max. Dienste mitziehen; "Auto" (None) clampt nie
            if (s.min_shifts is not None and s.max_shifts is not None
                    and s.max_shifts < s.min_shifts):
                s.max_shifts = s.min_shifts
                other = self._steppers.get((profile_idx, assistant_id, "max_target"))
                if other:
                    other.set_value(s.min_shifts)
        elif field == "max_target":
            s.max_shifts = None if value < 0 else value
            if (s.max_shifts is not None and s.min_shifts is not None
                    and s.min_shifts > s.max_shifts):
                s.min_shifts = s.max_shifts
                other = self._steppers.get((profile_idx, assistant_id, "min_target"))
                if other:
                    other.set_value(s.max_shifts)
        elif field == "max":
            s.max_consecutive_days = value
            # Min. Block darf nicht groesser sein als Max. Folge
            if s.min_block_days > value:
                s.min_block_days = value
                other = self._steppers.get((profile_idx, assistant_id, "min"))
                if other:
                    other.set_value(value)
        elif field == "min":
            s.min_block_days = value
            if s.max_consecutive_days < value:
                s.max_consecutive_days = value
                other = self._steppers.get((profile_idx, assistant_id, "max"))
                if other:
                    other.set_value(value)
        elif field == "gap":
            s.min_gap_days = value

        self.profiles_changed.emit()

    def on_attach_changed(self, profile_idx: int, assistant_id: str, value: str):
        s = self._profile_settings(profile_idx, assistant_id)
        s.oncall_attach = value
        self.profiles_changed.emit()

    def on_name_edited(self, profile_idx: int, item: QTableWidgetItem):
        """Namensaenderung in einer der beiden Tabellen sofort uebernehmen
        und in der anderen Tabelle spiegeln."""
        if self._refreshing or item.column() != 1 or not self.plan:
            return
        row = item.row()
        if row >= len(self.plan.assistants):
            return
        assistant = self.plan.assistants[row]
        if assistant.name == item.text():
            return
        assistant.name = item.text()
        other = self._tables[1 - profile_idx].item(row, 1)
        if other is not None:
            self._refreshing = True
            other.setText(assistant.name)
            self._refreshing = False
        self.refresh_vacations()
        self.assistants_changed.emit()

    def refresh_table(self):
        if not self.plan:
            return

        self._refreshing = True
        self._steppers = {}

        if self.plan:
            month_text = f"{self.plan.year}-{self.plan.month:02d}"
            for btn in self._apply_buttons:
                btn.setText(f"In Dienstplan {month_text} uebernehmen")

        for profile_idx, table in enumerate(self._tables):
            self.profile_tabs.setTabText(
                profile_idx, self.profiles[profile_idx].name
            )
            table.setRowCount(len(self.plan.assistants))
            table.verticalHeader().setDefaultSectionSize(theme.ROW_HEIGHT)

            for i, assistant in enumerate(self.plan.assistants):
                s = self._profile_settings(profile_idx, assistant.id)

                color_btn = ColorButton(assistant.color)
                color_btn.color_changed.connect(
                    lambda new_color, aid=assistant.id:
                    self.update_assistant_color(aid, new_color)
                )
                table.setCellWidget(i, 0, color_btn)

                table.setItem(i, 1, QTableWidgetItem(assistant.name))

                table.setCellWidget(i, 2, self._make_stepper(
                    profile_idx, assistant, "min_target", "Min. Dienste",
                    -1 if s.min_shifts is None else s.min_shifts, -1, 31,
                    special_min_text="Auto",
                ))
                table.setCellWidget(i, 3, self._make_stepper(
                    profile_idx, assistant, "max_target", "Max. Dienste",
                    -1 if s.max_shifts is None else s.max_shifts, -1, 31,
                    special_min_text="Auto",
                ))
                table.setCellWidget(i, 4, self._make_stepper(
                    profile_idx, assistant, "max", "Max. Folge",
                    s.max_consecutive_days, 1, 7,
                ))
                table.setCellWidget(i, 5, self._make_stepper(
                    profile_idx, assistant, "min", "Min. Block",
                    s.min_block_days, 1, 7,
                ))
                gap_stepper = self._make_stepper(
                    profile_idx, assistant, "gap", "Abstand",
                    s.min_gap_days, 0, 14, special_min_text="Aus",
                )
                gap_stepper.setToolTip(
                    "Mindestabstand in freien Tagen zwischen zwei "
                    "Einsatzbloecken dieser Person (Dienst und "
                    "Rufbereitschaft zusammen). Harte Regel."
                )
                table.setCellWidget(i, 6, gap_stepper)

                attach_combo = QComboBox()
                for label, value in ATTACH_OPTIONS:
                    attach_combo.addItem(label, value)
                index = attach_combo.findData(s.oncall_attach)
                attach_combo.setCurrentIndex(index if index >= 0 else 0)
                attach_combo.setToolTip(
                    "Rufbereitschaft als Block direkt vor bzw. nach dem "
                    "Dienstblock einplanen - fuer Helfer mit weiter "
                    "Anreise, die am Stueck vor Ort sein wollen."
                )
                attach_combo.currentIndexChanged.connect(
                    lambda _, c=attach_combo, p=profile_idx, aid=assistant.id:
                    self.on_attach_changed(p, aid, c.currentData())
                )
                table.setCellWidget(i, 7, attach_combo)

            # Kompakte Spalten: schmale Namensspalte, Rest nach Inhalt;
            # rechts darf Rand bleiben
            header = table.horizontalHeader()
            header.setStretchLastSection(False)
            header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
            stepper_width = 2 * theme.STEPPER_BUTTON_W + 64
            table.setColumnWidth(0, 70)
            table.setColumnWidth(1, 150)
            for col in (2, 3, 4, 5, 6):
                table.setColumnWidth(col, stepper_width)
            table.setColumnWidth(7, 140)

        self._refreshing = False
        self.add_btn.setEnabled(len(self.plan.assistants) < 10)

    def apply_profile(self, profile_idx: int):
        """Uebertraegt die Vorlage in den Dienstplan des aktuellen Monats."""
        if not self.plan:
            return
        profile = self.profiles[profile_idx]
        for assistant in self.plan.assistants:
            apply_settings(
                assistant.constraints,
                profile.settings.setdefault(assistant.id, AssistantSettings()),
            )
        self.assistants_changed.emit()
        QMessageBox.information(
            self, "Uebernommen",
            f"Die Einstellungen aus '{profile.name}' gelten jetzt fuer den "
            f"Dienstplan {self.plan.year}-{self.plan.month:02d}.",
        )

    def add_assistant(self):
        if not self.plan or len(self.plan.assistants) >= 10:
            return

        new_id = str(uuid.uuid4())[:8]
        constraints = AssistantConstraints(assistant_id=new_id)
        assistant = Assistant(
            id=new_id,
            name="Neuer Helfer",
            color="#3498DB",
            constraints=constraints,
        )
        self.plan.assistants.append(assistant)
        self.refresh_table()
        self.assistants_changed.emit()

    def remove_assistant(self):
        if not self.plan:
            return

        table = self._tables[self.profile_tabs.currentIndex()]
        row = table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Warnung", "Bitte waehlen Sie einen Helfer aus.")
            return

        removed = self.plan.assistants[row]
        del self.plan.assistants[row]
        for profile in self.profiles:
            profile.settings.pop(removed.id, None)
        self.refresh_table()
        self.refresh_vacations()
        self.assistants_changed.emit()

    def update_assistant_color(self, assistant_id: str, color: str):
        assistant = self._assistant_by_id(assistant_id)
        if assistant is None:
            return
        assistant.color = color
        # Farbknopf der jeweils anderen Tabelle mitziehen
        row = self.plan.assistants.index(assistant)
        for table in self._tables:
            widget = table.cellWidget(row, 0)
            if isinstance(widget, ColorButton) and widget.current_color != color:
                widget.set_color(color)
        self.refresh_vacations()
        self.assistants_changed.emit()

    # --- Abwesenheiten (Urlaub + Block) ---

    def _all_absences(self) -> list[tuple]:
        """Alle Abwesenheiten aller Helfer als (start, end, assistant, kind),
        chronologisch: Zeitraeume und Einzeltage, Urlaub und Block."""
        absences = []
        for assistant in self.plan.assistants:
            c = assistant.constraints
            for start, end in c.vacation_ranges:
                absences.append((start, end, assistant, "urlaub"))
            for d in c.unavailable_dates:
                absences.append((d, d, assistant, "urlaub"))
            for start, end in c.blocked_ranges:
                absences.append((start, end, assistant, "block"))
            for d in c.blocked_dates:
                absences.append((d, d, assistant, "block"))
        absences.sort(key=lambda v: (v[0], v[1], v[2].name))
        return absences

    def _refresh_filter_combos(self, absences: list[tuple]):
        """Befuellt Personen- und Monatsfilter neu, Auswahl bleibt erhalten."""
        person_combo, month_combo = self.filter_person_combo, self.filter_month_combo
        selected_person = person_combo.currentData()
        selected_month = month_combo.currentData()

        person_combo.blockSignals(True)
        person_combo.clear()
        person_combo.addItem("Alle Helfer", None)
        for assistant in self.plan.assistants:
            pixmap = QPixmap(12, 12)
            pixmap.fill(QColor(assistant.color))
            person_combo.addItem(pixmap, assistant.name, assistant.id)
        index = person_combo.findData(selected_person)
        person_combo.setCurrentIndex(index if index >= 0 else 0)
        person_combo.blockSignals(False)

        months = []
        for start, end, _, _ in absences:
            cursor = date(start.year, start.month, 1)
            while cursor <= end:
                if (cursor.year, cursor.month) not in months:
                    months.append((cursor.year, cursor.month))
                cursor = date(
                    cursor.year + (cursor.month == 12),
                    cursor.month % 12 + 1, 1,
                )
        months.sort()

        month_names = ["", "Januar", "Februar", "Maerz", "April", "Mai", "Juni",
                       "Juli", "August", "September", "Oktober", "November", "Dezember"]
        month_combo.blockSignals(True)
        month_combo.clear()
        month_combo.addItem("Alle Monate", None)
        for year, month in months:
            # String statt Tupel: findData vergleicht Strings zuverlaessig
            month_combo.addItem(f"{month_names[month]} {year}", f"{year:04d}-{month:02d}")
        index = month_combo.findData(selected_month)
        month_combo.setCurrentIndex(index if index >= 0 else 0)
        month_combo.blockSignals(False)

    def refresh_vacations(self):
        """Abwesenheitsliste: gefiltert nach Person/Monat, Vergangenes optional."""
        self.vacation_list.clear()
        if not self.plan:
            return

        absences = self._all_absences()
        self._refresh_filter_combos(absences)

        person_filter = self.filter_person_combo.currentData()
        month_filter = self.filter_month_combo.currentData()
        show_past = self.show_past_btn.isChecked()
        today = date.today()

        for start, end, assistant, kind in absences:
            if person_filter is not None and assistant.id != person_filter:
                continue
            if month_filter is not None:
                year, month = int(month_filter[:4]), int(month_filter[5:7])
                month_start = date(year, month, 1)
                month_end = date(year, month, calendar.monthrange(year, month)[1])
                if end < month_start or start > month_end:
                    continue
            if not show_past and end < today:
                continue

            if start == end:
                text = "{:%d.%m.%Y}   {}".format(start, assistant.name)
            else:
                text = "{:%d.%m.%Y} - {:%d.%m.%Y}   {}".format(start, end, assistant.name)
            if kind == "block":
                text += "   [Block]"
            item = QListWidgetItem(text)
            item.setData(
                Qt.ItemDataRole.UserRole,
                (assistant.id, start.isoformat(), end.isoformat(), kind),
            )
            # Farbpunkt des Helfers als Markierung
            pixmap = QPixmap(12, 12)
            pixmap.fill(QColor(assistant.color))
            item.setIcon(pixmap)
            self.vacation_list.addItem(item)

    def _vacation_dialog(self, title: str, assistant_id: str | None = None,
                         start: date | None = None,
                         end: date | None = None,
                         kind: str = "urlaub") -> tuple[str, date, date, str] | None:
        """Dialog fuer Abwesenheit anlegen/bearbeiten. Gibt
        (assistant_id, von, bis, kind) zurueck oder None bei Abbruch."""
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        layout = QVBoxLayout()

        h0 = QHBoxLayout()
        h0.addWidget(QLabel("Helfer:"))
        assistant_combo = QComboBox()
        for assistant in self.plan.assistants:
            pixmap = QPixmap(12, 12)
            pixmap.fill(QColor(assistant.color))
            assistant_combo.addItem(pixmap, assistant.name, assistant.id)
        if assistant_id is not None:
            index = assistant_combo.findData(assistant_id)
            if index >= 0:
                assistant_combo.setCurrentIndex(index)
        h0.addWidget(assistant_combo)
        h0.addWidget(QLabel("Art:"))
        kind_combo = QComboBox()
        kind_combo.addItem("Urlaub", "urlaub")
        kind_combo.addItem("Block", "block")
        index = kind_combo.findData(kind)
        if index >= 0:
            kind_combo.setCurrentIndex(index)
        h0.addWidget(kind_combo)
        h0.addStretch()
        layout.addLayout(h0)

        default_start = start or date(self.plan.year, self.plan.month, 1)
        default_end = end or default_start
        h1 = QHBoxLayout()
        h1.addWidget(QLabel("Von:"))
        start_edit = QDateEdit(QDate(default_start.year, default_start.month, default_start.day))
        start_edit.setCalendarPopup(True)
        h1.addWidget(start_edit)
        h1.addWidget(QLabel("Bis:"))
        end_edit = QDateEdit(QDate(default_end.year, default_end.month, default_end.day))
        end_edit.setCalendarPopup(True)
        h1.addWidget(end_edit)
        h1.addStretch()
        layout.addLayout(h1)

        # Bis-Datum mitziehen, wenn Von hinter Bis liegt
        start_edit.dateChanged.connect(
            lambda d: end_edit.setDate(d) if end_edit.date() < d else None
        )

        button_layout = QHBoxLayout()
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(dialog.accept)
        cancel_btn = QPushButton("Abbrechen")
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addStretch()
        button_layout.addWidget(ok_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

        dialog.setLayout(layout)
        if not dialog.exec():
            return None

        new_start = start_edit.date().toPython()
        new_end = end_edit.date().toPython()
        if new_start > new_end:
            QMessageBox.warning(self, "Fehler", "Startdatum muss vor dem Enddatum liegen.")
            return None
        return assistant_combo.currentData(), new_start, new_end, kind_combo.currentData()

    def _assistant_by_id(self, assistant_id: str) -> Assistant | None:
        return next((a for a in self.plan.assistants if a.id == assistant_id), None)

    def _add_range(self, assistant: Assistant, start: date, end: date, kind: str):
        get_days = absence_days if kind == "urlaub" else blocked_days
        set_days = set_absence_days if kind == "urlaub" else set_blocked_days
        days = get_days(assistant.constraints)
        d = start
        while d <= end:
            days.add(d)
            d += timedelta(days=1)
        set_days(assistant.constraints, days)

    def _remove_absence(self, assistant: Assistant, start: date, end: date, kind: str):
        """Entfernt einen Listeneintrag: Einzeltag oder Zeitraum."""
        if assistant is None:
            return
        c = assistant.constraints
        if kind == "block":
            singles, ranges = c.blocked_dates, c.blocked_ranges
        else:
            singles, ranges = c.unavailable_dates, c.vacation_ranges
        if start == end and start in singles:
            singles.remove(start)
        elif (start, end) in ranges:
            ranges.remove((start, end))

    def add_vacation(self):
        if not self.plan or not self.plan.assistants:
            QMessageBox.warning(self, "Warnung", "Bitte zuerst Helfer anlegen.")
            return

        result = self._vacation_dialog("Abwesenheit hinzufuegen")
        if result is None:
            return
        assistant_id, start, end, kind = result
        self._add_range(self._assistant_by_id(assistant_id), start, end, kind)
        self.refresh_vacations()
        self.assistants_changed.emit()

    def edit_vacation(self):
        item = self.vacation_list.currentItem()
        if not item:
            QMessageBox.warning(self, "Warnung", "Bitte waehlen Sie eine Abwesenheit aus.")
            return

        old_id, start_iso, end_iso, old_kind = item.data(Qt.ItemDataRole.UserRole)
        old_start = date.fromisoformat(start_iso)
        old_end = date.fromisoformat(end_iso)

        result = self._vacation_dialog(
            "Abwesenheit bearbeiten", assistant_id=old_id,
            start=old_start, end=old_end, kind=old_kind,
        )
        if result is None:
            return
        new_id, new_start, new_end, new_kind = result

        self._remove_absence(self._assistant_by_id(old_id), old_start, old_end, old_kind)
        self._add_range(self._assistant_by_id(new_id), new_start, new_end, new_kind)
        self.refresh_vacations()
        self.assistants_changed.emit()

    def remove_vacation(self):
        item = self.vacation_list.currentItem()
        if not item:
            QMessageBox.warning(self, "Warnung", "Bitte waehlen Sie eine Abwesenheit aus.")
            return

        assistant_id, start_iso, end_iso, kind = item.data(Qt.ItemDataRole.UserRole)
        self._remove_absence(
            self._assistant_by_id(assistant_id),
            date.fromisoformat(start_iso),
            date.fromisoformat(end_iso),
            kind,
        )
        self.refresh_vacations()
        self.assistants_changed.emit()
