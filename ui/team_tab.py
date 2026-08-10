from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QMessageBox, QHeaderView,
    QGroupBox, QListWidget, QListWidgetItem, QDialog, QComboBox,
    QDateEdit, QLabel
)
from PySide6.QtCore import Qt, Signal, QDate
from PySide6.QtGui import QColor, QPixmap

from models import (
    Assistant, AssistantConstraints, MonthPlan,
    absence_days, set_absence_days, blocked_days, set_blocked_days,
)
from datetime import date, timedelta
import calendar
import uuid

from . import theme
from .widgets.color_button import ColorButton
from .widgets.big_stepper import BigStepper


class TeamTab(QWidget):
    assistants_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.plan: MonthPlan | None = None
        self._steppers = {}  # (assistant_id, field) -> BigStepper
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

        # Linke Seite: Helferliste mit Buttons
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

        # Tabelle: Werte direkt in der Zeile aenderbar (grosse +/- Buttons)
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            ["Farbe", "Name", "Min. Dienste", "Max. Dienste", "Max. Folge", "Min. Block"]
        )
        left_layout.addWidget(self.table)
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

    def refresh_all(self):
        """Von aussen aufrufen, wenn Einschraenkungen anderswo geaendert wurden."""
        self.refresh_table()
        self.refresh_vacations()

    # --- Team-Tabelle ---

    def _make_stepper(self, assistant, field: str, label: str, value: int,
                      minimum: int, maximum: int,
                      special_min_text: str | None = None) -> BigStepper:
        stepper = BigStepper(
            label=f"{assistant.name}: {label}",
            value=value, minimum=minimum, maximum=maximum,
            special_min_text=special_min_text,
        )
        stepper.value_changed.connect(
            lambda v, aid=assistant.id, f=field: self.on_stepper_changed(aid, f, v)
        )
        self._steppers[(assistant.id, field)] = stepper
        return stepper

    def on_stepper_changed(self, assistant_id: str, field: str, value: int):
        assistant = next((a for a in self.plan.assistants if a.id == assistant_id), None)
        if not assistant:
            return
        c = assistant.constraints

        if field == "min_target":
            c.min_shifts = None if value < 0 else value
            # Max. Dienste mitziehen; "Auto" (None) clampt nie
            if (c.min_shifts is not None and c.max_shifts is not None
                    and c.max_shifts < c.min_shifts):
                c.max_shifts = c.min_shifts
                other = self._steppers.get((assistant_id, "max_target"))
                if other:
                    other.set_value(c.min_shifts)
        elif field == "max_target":
            c.max_shifts = None if value < 0 else value
            if (c.max_shifts is not None and c.min_shifts is not None
                    and c.min_shifts > c.max_shifts):
                c.min_shifts = c.max_shifts
                other = self._steppers.get((assistant_id, "min_target"))
                if other:
                    other.set_value(c.max_shifts)
        elif field == "max":
            c.max_consecutive_days = value
            # Min. Block darf nicht groesser sein als Max. Folge
            if c.min_block_days > value:
                c.min_block_days = value
                other = self._steppers.get((assistant_id, "min"))
                if other:
                    other.set_value(value)
        elif field == "min":
            c.min_block_days = value
            if c.max_consecutive_days < value:
                c.max_consecutive_days = value
                other = self._steppers.get((assistant_id, "max"))
                if other:
                    other.set_value(value)

        self.assistants_changed.emit()

    def refresh_table(self):
        if not self.plan:
            return

        self._steppers = {}
        self.table.setRowCount(len(self.plan.assistants))
        self.table.verticalHeader().setDefaultSectionSize(theme.ROW_HEIGHT)

        for i, assistant in enumerate(self.plan.assistants):
            c = assistant.constraints

            color_btn = ColorButton(assistant.color)
            color_btn.color_changed.connect(
                lambda new_color, idx=i: self.update_assistant_color(idx, new_color)
            )
            self.table.setCellWidget(i, 0, color_btn)

            name_item = QTableWidgetItem(assistant.name)
            self.table.setItem(i, 1, name_item)

            self.table.setCellWidget(i, 2, self._make_stepper(
                assistant, "min_target", "Min. Dienste",
                -1 if c.min_shifts is None else c.min_shifts, -1, 31,
                special_min_text="Auto",
            ))
            self.table.setCellWidget(i, 3, self._make_stepper(
                assistant, "max_target", "Max. Dienste",
                -1 if c.max_shifts is None else c.max_shifts, -1, 31,
                special_min_text="Auto",
            ))
            self.table.setCellWidget(i, 4, self._make_stepper(
                assistant, "max", "Max. Folge", c.max_consecutive_days, 1, 7,
            ))
            self.table.setCellWidget(i, 5, self._make_stepper(
                assistant, "min", "Min. Block", c.min_block_days, 1, 7,
            ))

        # Kompakte Spalten: schmale Namensspalte, Rest nach Inhalt;
        # rechts darf Rand bleiben
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        stepper_width = 2 * theme.STEPPER_BUTTON_W + 64
        self.table.setColumnWidth(0, 70)
        self.table.setColumnWidth(1, 150)
        for col in (2, 3, 4, 5):
            self.table.setColumnWidth(col, stepper_width)

        self.add_btn.setEnabled(len(self.plan.assistants) < 10)

    def add_assistant(self):
        if not self.plan or len(self.plan.assistants) >= 10:
            return

        self._save_names_from_table()

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

        self._save_names_from_table()

        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Warnung", "Bitte waehlen Sie einen Helfer aus.")
            return

        del self.plan.assistants[row]
        self.refresh_table()
        self.refresh_vacations()
        self.assistants_changed.emit()

    def update_assistant_color(self, row: int, color: str):
        if self.plan and 0 <= row < len(self.plan.assistants):
            self.plan.assistants[row].color = color
            self.refresh_vacations()
            self.assistants_changed.emit()

    def _save_names_from_table(self):
        if not self.plan:
            return
        for i in range(self.table.rowCount()):
            name_item = self.table.item(i, 1)
            if name_item and i < len(self.plan.assistants):
                self.plan.assistants[i].name = name_item.text()

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
