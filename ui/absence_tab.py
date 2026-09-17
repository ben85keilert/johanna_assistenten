"""Tab "Urlaub": Abwesenheiten (Urlaub und Block) eintragen und einsehen.

Links ein Monatskalender in Wochenform - uebersichtlicher als das
Dienstplan-Raster und bewusst nur fuer die zwei Abwesenheitsarten. Rechts die
chronologische Liste aller Abwesenheiten mit Hinzufuegen/Bearbeiten/Entfernen.
Monat und Person werden oben in der Tab-Zeile gewaehlt.

Die Daten liegen wie bisher in den Constraints der Helfer (team.json,
monatsuebergreifend) - dieser Tab ist nur eine andere Sicht darauf.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QComboBox,
    QGroupBox, QListWidget, QListWidgetItem, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QMessageBox, QDialog, QDateEdit, QMenu,
)
from PySide6.QtCore import Qt, Signal, QDate
from PySide6.QtGui import QColor, QPixmap, QFont

from models import (
    Assistant, MonthPlan,
    absence_days, set_absence_days, blocked_days, set_blocked_days,
    holiday_name,
)
from persistence import AppSettings
from datetime import date, timedelta
import calendar

from . import theme
from .widgets.month_selector import MonthSelector

WEEKDAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]

# Stempel des Tabs
STAMP_VACATION = "urlaub"
STAMP_BLOCK = "block"
STAMP_CLEAR = "clear"

MIXED_COLOR = QColor(224, 224, 224)      # Urlaub+Block (nur in der Alle-Ansicht)
OUTSIDE_COLOR = QColor(245, 245, 245)    # Tag gehoert nicht zum Monat


class AbsenceTab(QWidget):
    # Abwesenheiten geaendert -> Plan neu zeichnen und als geaendert markieren
    absences_changed = Signal()

    def __init__(self, settings: AppSettings, parent=None):
        super().__init__(parent)
        self.plan: MonthPlan | None = None
        # Urlaub-/Block-Farbe kommen aus Einstellungen > Farben
        self.settings = settings
        self.year = date.today().year
        self.month = date.today().month
        self.active_stamp: str | None = None
        self._building = False
        self.init_ui()

    # --- Aufbau ---------------------------------------------------------

    def _init_top_bar(self):
        """Monat, Person und Listenfilter; sitzt in der Tab-Zeile
        (Corner-Widget), sichtbar solange dieser Tab aktiv ist."""
        self.top_bar = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 8, 0)

        self.month_selector = MonthSelector()
        self.month_selector.layout().setContentsMargins(0, 0, 0, 0)
        self.month_selector.month_changed.connect(self.on_month_changed)
        layout.addWidget(self.month_selector)

        layout.addWidget(QLabel("Person:"))
        self.person_combo = QComboBox()
        self.person_combo.setToolTip(
            "Wessen Abwesenheiten im Kalender gezeigt und eingetragen werden."
        )
        self.person_combo.currentIndexChanged.connect(self.on_person_changed)
        layout.addWidget(self.person_combo)

        self.only_month_btn = QPushButton("Nur dieser Monat")
        self.only_month_btn.setCheckable(True)
        self.only_month_btn.setToolTip(
            "Liste rechts auf den oben gewaehlten Monat beschraenken."
        )
        self.only_month_btn.toggled.connect(self.refresh_list)
        layout.addWidget(self.only_month_btn)

        self.show_past_btn = QPushButton("Vergangene anzeigen")
        self.show_past_btn.setCheckable(True)
        self.show_past_btn.setToolTip(
            "Bereits abgelaufene Abwesenheiten ein-/ausblenden."
        )
        self.show_past_btn.toggled.connect(self.refresh_list)
        layout.addWidget(self.show_past_btn)

        self.top_bar.setLayout(layout)

    def init_ui(self):
        self._init_top_bar()
        layout = QHBoxLayout()

        # --- Links: Kalender ---
        calendar_group = QGroupBox("Kalender")
        calendar_layout = QVBoxLayout()

        stamp_layout = QHBoxLayout()
        stamp_layout.addWidget(QLabel("Eintragen:"))
        self.stamp_buttons = {}
        for stamp, label, tip in [
            (STAMP_VACATION, "Urlaub",
             "Tag anklicken: Urlaub setzen bzw. wieder entfernen."),
            (STAMP_BLOCK, "Block",
             "Tag anklicken: Block setzen bzw. wieder entfernen "
             "(zweite Abwesenheitsart neben Urlaub)."),
            (STAMP_CLEAR, "Loeschen",
             "Tag anklicken: Urlaub oder Block dieses Tages entfernen."),
        ]:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setToolTip(tip)
            btn.toggled.connect(lambda checked, s=stamp: self.on_stamp_toggled(s, checked))
            self.stamp_buttons[stamp] = btn
            stamp_layout.addWidget(btn)

        self.hint_label = QLabel()
        self.hint_label.setStyleSheet("color: #B05000;")
        stamp_layout.addWidget(self.hint_label)
        stamp_layout.addStretch()
        calendar_layout.addLayout(stamp_layout)

        self.calendar = QTableWidget()
        self.calendar.setColumnCount(7)
        self.calendar.setHorizontalHeaderLabels(WEEKDAYS)
        self.calendar.setRowCount(6)
        self.calendar.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.calendar.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.calendar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.calendar.customContextMenuRequested.connect(self.show_context_menu)
        self.calendar.cellClicked.connect(self.on_cell_clicked)
        self.calendar.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.calendar.verticalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        calendar_layout.addWidget(self.calendar)

        self.legend_label = QLabel()
        calendar_layout.addWidget(self.legend_label)
        self._update_legend()

        calendar_group.setLayout(calendar_layout)
        layout.addWidget(calendar_group, stretch=3)

        # --- Rechts: chronologische Liste ---
        list_group = QGroupBox("Abwesenheiten (chronologisch)")
        list_layout = QVBoxLayout()
        self.absence_list = QListWidget()
        self.absence_list.itemDoubleClicked.connect(lambda _: self.edit_absence())
        self.absence_list.itemSelectionChanged.connect(self.on_list_selection)
        list_layout.addWidget(self.absence_list)

        list_buttons = QHBoxLayout()
        self.add_btn = QPushButton("+ Hinzufuegen")
        self.add_btn.clicked.connect(self.add_absence)
        list_buttons.addWidget(self.add_btn)
        self.edit_btn = QPushButton("Bearbeiten")
        self.edit_btn.clicked.connect(self.edit_absence)
        list_buttons.addWidget(self.edit_btn)
        self.remove_btn = QPushButton("- Entfernen")
        self.remove_btn.clicked.connect(self.remove_absence_entry)
        list_buttons.addWidget(self.remove_btn)
        list_buttons.addStretch()
        list_layout.addLayout(list_buttons)

        list_group.setLayout(list_layout)
        layout.addWidget(list_group, stretch=2)

        self.setLayout(layout)

    # --- Aussenschnittstelle -------------------------------------------

    def set_plan(self, plan: MonthPlan):
        """Neuer Monatsplan: Kalender folgt dem Monat des Dienstplans."""
        self.plan = plan
        self.year, self.month = plan.year, plan.month
        self.month_selector.set_month(self.year, self.month)
        self.refresh_all()

    def refresh_all(self):
        self._refresh_person_combo()
        self.refresh_calendar()
        self.refresh_list()

    def _vacation_color(self) -> QColor:
        return QColor(self.settings.entry_colors.get("VACATION", "#81C784"))

    def _block_color(self) -> QColor:
        return QColor(self.settings.entry_colors.get("BLOCK", "#E57373"))

    def _update_legend(self):
        # Farbige Kaestchen in der Legende folgen den eingestellten Farben
        self.legend_label.setText(
            f'<span style="background-color:{self._vacation_color().name()};">'
            "&nbsp;&nbsp;&nbsp;</span> Urlaub &nbsp;&nbsp; "
            f'<span style="background-color:{self._block_color().name()};">'
            "&nbsp;&nbsp;&nbsp;</span> Block &nbsp;&nbsp; "
            "Mehrfachauswahl mit Strg/Shift, dann Rechtsklick"
        )

    # --- Kopfzeile ------------------------------------------------------

    def on_month_changed(self, year: int, month: int):
        self.year, self.month = year, month
        self.refresh_calendar()
        self.refresh_list()

    def on_person_changed(self):
        self.refresh_calendar()
        self.refresh_list()

    def _refresh_person_combo(self):
        """Personenliste neu aufbauen, Auswahl bleibt erhalten."""
        if not self.plan:
            return
        selected = self.person_combo.currentData()
        self.person_combo.blockSignals(True)
        self.person_combo.clear()
        self.person_combo.addItem("Alle Helfer", None)
        for assistant in self.plan.assistants:
            pixmap = QPixmap(12, 12)
            pixmap.fill(QColor(assistant.color))
            self.person_combo.addItem(pixmap, assistant.name, assistant.id)
        index = self.person_combo.findData(selected)
        self.person_combo.setCurrentIndex(index if index >= 0 else 0)
        self.person_combo.blockSignals(False)

    def _selected_assistant(self) -> Assistant | None:
        """Die im Kopf gewaehlte Person; None = "Alle Helfer"."""
        return self._assistant_by_id(self.person_combo.currentData())

    def _assistant_by_id(self, assistant_id) -> Assistant | None:
        if not self.plan or assistant_id is None:
            return None
        return next((a for a in self.plan.assistants if a.id == assistant_id), None)

    # --- Stempel --------------------------------------------------------

    def on_stamp_toggled(self, stamp: str, checked: bool):
        if self._building:
            return
        if checked:
            # Exklusiv, aber abwaehlbar (wie im Dienstplan)
            for other, btn in self.stamp_buttons.items():
                if other != stamp and btn.isChecked():
                    btn.setChecked(False)
            self.active_stamp = stamp
        elif self.active_stamp == stamp:
            self.active_stamp = None
        self._update_hint()

    def _update_hint(self):
        if self._selected_assistant() is None:
            self.hint_label.setText("Zum Eintragen oben eine Person waehlen")
        elif self.active_stamp is None:
            self.hint_label.setText("")
        else:
            self.hint_label.setText("")

    def on_cell_clicked(self, row: int, col: int):
        if self.active_stamp is None:
            return
        item = self.calendar.item(row, col)
        day = item.data(Qt.ItemDataRole.UserRole) if item else None
        if day is None:
            return
        assistant = self._selected_assistant()
        if assistant is None:
            self._update_hint()
            return
        self.apply_stamp(self.active_stamp, [day], assistant)

    def _selected_days(self, fallback_pos=None) -> list[int]:
        days = []
        for item in self.calendar.selectedItems():
            day = item.data(Qt.ItemDataRole.UserRole)
            if day is not None:
                days.append(day)
        if not days and fallback_pos is not None:
            item = self.calendar.itemAt(fallback_pos)
            if item is not None:
                day = item.data(Qt.ItemDataRole.UserRole)
                if day is not None:
                    days.append(day)
        return sorted(days)

    def show_context_menu(self, pos):
        days = self._selected_days(fallback_pos=pos)
        if not days:
            return
        assistant = self._selected_assistant()
        if assistant is None:
            QMessageBox.information(
                self, "Person waehlen",
                "Bitte oben eine Person waehlen, deren Abwesenheiten "
                "eingetragen werden sollen.",
            )
            return

        suffix = f" ({len(days)} Tage)" if len(days) > 1 else ""
        menu = QMenu()
        menu.addAction(
            f"Urlaub setzen{suffix}",
            lambda: self.apply_stamp(STAMP_VACATION, days, assistant, toggle=False),
        )
        menu.addAction(
            f"Block setzen{suffix}",
            lambda: self.apply_stamp(STAMP_BLOCK, days, assistant, toggle=False),
        )
        menu.addSeparator()
        menu.addAction(
            f"Abwesenheit entfernen{suffix}",
            lambda: self.apply_stamp(STAMP_CLEAR, days, assistant),
        )
        menu.exec(self.calendar.mapToGlobal(pos))

    def apply_stamp(self, stamp: str, days: list[int], assistant: Assistant,
                    toggle: bool = True):
        """Setzt/entfernt Urlaub oder Block an den Tagen dieses Monats.

        toggle=True (Klick): ein bereits gesetzter Tag wird wieder entfernt.
        toggle=False (Kontextmenue): setzt fuer alle Tage der Auswahl.
        Urlaub und Block schliessen sich gegenseitig aus.
        """
        c = assistant.constraints
        vacation = absence_days(c)
        blocked = blocked_days(c)
        changed = False

        for day in days:
            d = date(self.year, self.month, day)
            if stamp == STAMP_CLEAR:
                if d in vacation:
                    vacation.discard(d)
                    changed = True
                if d in blocked:
                    blocked.discard(d)
                    changed = True
                continue

            target, other = (
                (vacation, blocked) if stamp == STAMP_VACATION else (blocked, vacation)
            )
            if d in target:
                if toggle:
                    target.discard(d)
                    changed = True
                continue
            target.add(d)
            other.discard(d)
            changed = True

        if not changed:
            return

        # Zusammenhaengende Tage werden dabei zu Zeitraeumen zusammengefasst
        set_absence_days(c, vacation)
        set_blocked_days(c, blocked)
        self.refresh_calendar()
        self.refresh_list()
        self.absences_changed.emit()

    # --- Kalender -------------------------------------------------------

    def _day_state(self, day: int) -> tuple[QColor | None, list[str]]:
        """Farbe und Beschriftungszeilen fuer einen Tag.

        Mit gewaehlter Person: deren Zustand. Ohne Auswahl: alle Helfer,
        die an diesem Tag abwesend sind.
        """
        d = date(self.year, self.month, day)
        person = self._selected_assistant()
        if person is not None:
            if d in absence_days(person.constraints):
                return self._vacation_color(), ["Urlaub"]
            if d in blocked_days(person.constraints):
                return self._block_color(), ["Block"]
            return None, []

        lines, has_vacation, has_block = [], False, False
        for assistant in self.plan.assistants:
            if d in absence_days(assistant.constraints):
                lines.append(f"U {assistant.name}")
                has_vacation = True
            elif d in blocked_days(assistant.constraints):
                lines.append(f"B {assistant.name}")
                has_block = True
        if not lines:
            return None, []
        if has_vacation and has_block:
            color = MIXED_COLOR
        else:
            color = self._vacation_color() if has_vacation else self._block_color()
        return color, lines

    def refresh_calendar(self):
        if not self.plan:
            return

        self._building = True
        self.calendar.clearContents()
        days_in_month = calendar.monthrange(self.year, self.month)[1]
        first_weekday = date(self.year, self.month, 1).weekday()  # Mo = 0
        weeks = (first_weekday + days_in_month + 6) // 7
        self.calendar.setRowCount(weeks)

        today = date.today()
        small = QFont()
        small.setPointSize(max(7, theme.FONT_PT - 2))

        week_labels = []
        for week in range(weeks):
            for weekday in range(7):
                day = week * 7 + weekday - first_weekday + 1
                item = QTableWidgetItem()
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
                )
                if day < 1 or day > days_in_month:
                    item.setFlags(Qt.ItemFlag.NoItemFlags)
                    item.setBackground(OUTSIDE_COLOR)
                else:
                    color, lines = self._day_state(day)
                    holiday = holiday_name(self.year, self.month, day)
                    item.setData(Qt.ItemDataRole.UserRole, day)
                    item.setText("\n".join([str(day)] + lines))
                    item.setFont(small)
                    if color is not None:
                        item.setBackground(color)
                    elif weekday >= 5 or holiday is not None:
                        # Feiertage grau wie Wochenenden (reine Anzeige)
                        item.setBackground(theme.WEEKEND_COLOR)
                    tooltip = [holiday] if holiday else []
                    if date(self.year, self.month, day) == today:
                        bold = QFont(small)
                        bold.setBold(True)
                        item.setFont(bold)
                        tooltip.append("Heute")
                    if tooltip:
                        item.setToolTip("\n".join(tooltip))
                self.calendar.setItem(week, weekday, item)

            # Zeilenkopf: Kalenderwoche
            monday_offset = week * 7 - first_weekday + 1
            reference = min(max(monday_offset, 1), days_in_month)
            week_labels.append(
                f"KW {date(self.year, self.month, reference).isocalendar()[1]}"
            )
        self.calendar.setVerticalHeaderLabels(week_labels)

        self._building = False
        self._update_legend()
        self._update_hint()

    # --- Liste ----------------------------------------------------------

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

    def refresh_list(self):
        """Liste: gefiltert nach Person, optional Monat und Vergangenes."""
        if not self.plan:
            return
        self.absence_list.clear()

        person_filter = self.person_combo.currentData()
        only_month = self.only_month_btn.isChecked()
        show_past = self.show_past_btn.isChecked()
        today = date.today()
        month_start = date(self.year, self.month, 1)
        month_end = date(
            self.year, self.month, calendar.monthrange(self.year, self.month)[1]
        )

        for start, end, assistant, kind in self._all_absences():
            if person_filter is not None and assistant.id != person_filter:
                continue
            if only_month and (end < month_start or start > month_end):
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
            pixmap = QPixmap(12, 12)
            pixmap.fill(QColor(assistant.color))
            item.setIcon(pixmap)
            self.absence_list.addItem(item)

    def on_list_selection(self):
        """Listenauswahl zeigt den passenden Monat im Kalender."""
        item = self.absence_list.currentItem()
        if item is None:
            return
        _, start_iso, _, _ = item.data(Qt.ItemDataRole.UserRole)
        start = date.fromisoformat(start_iso)
        if (start.year, start.month) != (self.year, self.month):
            self.year, self.month = start.year, start.month
            self.month_selector.set_month(self.year, self.month)
            self.refresh_calendar()

    # --- Anlegen / Bearbeiten / Entfernen -------------------------------

    def _absence_dialog(self, title: str, assistant_id: str | None = None,
                        start: date | None = None, end: date | None = None,
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
        preset = assistant_id if assistant_id is not None else self.person_combo.currentData()
        if preset is not None:
            index = assistant_combo.findData(preset)
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

        default_start = start or date(self.year, self.month, 1)
        default_end = end or default_start
        h1 = QHBoxLayout()
        h1.addWidget(QLabel("Von:"))
        start_edit = QDateEdit(
            QDate(default_start.year, default_start.month, default_start.day)
        )
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

    def _add_range(self, assistant: Assistant, start: date, end: date, kind: str):
        if assistant is None:
            return
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

    def add_absence(self):
        if not self.plan or not self.plan.assistants:
            QMessageBox.warning(self, "Warnung", "Bitte zuerst Helfer anlegen.")
            return

        result = self._absence_dialog("Abwesenheit hinzufuegen")
        if result is None:
            return
        assistant_id, start, end, kind = result
        self._add_range(self._assistant_by_id(assistant_id), start, end, kind)
        self.refresh_calendar()
        self.refresh_list()
        self.absences_changed.emit()

    def edit_absence(self):
        item = self.absence_list.currentItem()
        if not item:
            QMessageBox.warning(self, "Warnung", "Bitte waehlen Sie eine Abwesenheit aus.")
            return

        old_id, start_iso, end_iso, old_kind = item.data(Qt.ItemDataRole.UserRole)
        old_start = date.fromisoformat(start_iso)
        old_end = date.fromisoformat(end_iso)

        result = self._absence_dialog(
            "Abwesenheit bearbeiten", assistant_id=old_id,
            start=old_start, end=old_end, kind=old_kind,
        )
        if result is None:
            return
        new_id, new_start, new_end, new_kind = result

        self._remove_absence(self._assistant_by_id(old_id), old_start, old_end, old_kind)
        self._add_range(self._assistant_by_id(new_id), new_start, new_end, new_kind)
        self.refresh_calendar()
        self.refresh_list()
        self.absences_changed.emit()

    def remove_absence_entry(self):
        item = self.absence_list.currentItem()
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
        self.refresh_calendar()
        self.refresh_list()
        self.absences_changed.emit()
