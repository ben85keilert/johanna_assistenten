"""Tab "Urlaub und Notizen": Abwesenheiten (Urlaub und Wunsch) sowie
Dienstwuensche (Positivwuensche) eintragen und einsehen, dazu alle
Tagesnotizen des Monats.

Links die Helfer-Buttons (fuer wen angezeigt und eingetragen wird; Strg+Klick
waehlt mehrere, "Alle" alle), daneben ein Monatskalender in Wochenform -
uebersichtlicher als das Dienstplan-Raster und bewusst nur fuer die zwei
Abwesenheitsarten. Rechts zwei Reiter: "Abwesenheiten" (chronologische Liste
mit Hinzufuegen/Bearbeiten/Entfernen) und "Notizen" (ui/notes_panel.py).
Der Monat ist immer der des Dienstplans (gemeinsamer Monatswaehler in der
Tab-Zeile).

Die Abwesenheiten liegen wie bisher in den Constraints der Helfer
(team.json, monatsuebergreifend) - dieser Tab ist nur eine andere Sicht
darauf. "Wunsch" ist die Oberflaechen-Bezeichnung der Freiwunsch-Tage
(intern weiter blocked_dates/blocked_ranges, Dateiformat unveraendert);
"Dienstwunsch" sind die Tage, an denen jemand gern Dienst macht
(wish_dates/wish_ranges). Ein Tag hat je Person hoechstens eine der drei
Arten (models.DAY_KINDS / set_day_kind).
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QComboBox,
    QGroupBox, QListWidget, QListWidgetItem, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QMessageBox, QDialog, QDateEdit, QMenu,
    QTabWidget, QApplication,
)
from PySide6.QtCore import Qt, Signal, QDate, QTimer
from PySide6.QtGui import QColor, QFont

from models import (
    Assistant, MonthPlan, DAY_KINDS, day_kind, set_day_kind, holiday_name,
)
from persistence import AppSettings, DEFAULT_ENTRY_COLORS
from datetime import date, timedelta
import calendar

from . import theme
from .notes_panel import NotesPanel

WEEKDAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]

# Stempel des Tabs: die drei Tagesarten (Schluessel wie models.DAY_KINDS)
# und Loeschen
STAMP_VACATION = "urlaub"
STAMP_BLOCK = "block"
STAMP_WISH = "wish"
STAMP_CLEAR = "clear"

# Beschriftung, Kuerzel (Kalender bei mehreren Helfern, Liste) und
# Farbschluessel (AppSettings.entry_colors) je Tagesart
KIND_LABELS = {"urlaub": "Urlaub", "block": "Wunsch", "wish": "Dienstwunsch"}
KIND_SHORT = {"urlaub": "U", "block": "W", "wish": "D"}
KIND_COLOR_KEYS = {"urlaub": "VACATION", "block": "BLOCK", "wish": "WISH"}


def _kind_lists(assistant: Assistant, kind: str) -> tuple[list, list]:
    """(Einzeltage, Zeitraeume) einer Tagesart - die Listen selbst, zum
    Entfernen einzelner Listeneintraege."""
    c = assistant.constraints
    if kind == "block":
        return c.blocked_dates, c.blocked_ranges
    if kind == "wish":
        return c.wish_dates, c.wish_ranges
    return c.unavailable_dates, c.vacation_ranges


class AbsenceTab(QWidget):
    # Abwesenheiten geaendert -> Plan neu zeichnen und als geaendert markieren
    absences_changed = Signal()
    # Weitergereicht aus dem Notizen-Reiter (NotesPanel)
    notes_changed = Signal()
    notes_export_requested = Signal()
    # Listeneintrag in einem anderen Monat angeklickt -> alle Tabs wechseln
    month_change_requested = Signal(int, int)

    def __init__(self, settings: AppSettings, parent=None):
        super().__init__(parent)
        self.plan: MonthPlan | None = None
        # Urlaub-/Wunsch-Farbe kommen aus Einstellungen > Farben
        self.settings = settings
        # Immer der Monat des Dienstplans (ein Monat fuer alle Tabs)
        self.year = date.today().year
        self.month = date.today().month
        self.active_stamp: str | None = None
        # Links gewaehlte Helfer: fuer sie wird angezeigt und eingetragen
        self._selected_ids: set[str] = set()
        self._person_buttons: dict[str, QPushButton] = {}
        self._building = False
        self.init_ui()

    # --- Aufbau ---------------------------------------------------------

    def init_ui(self):
        layout = QHBoxLayout()

        # --- Links: Helfer-Auswahl ---
        person_group = QGroupBox("Helfer")
        person_layout = QVBoxLayout()
        self.all_btn = QPushButton("Alle")
        self.all_btn.setCheckable(True)
        self.all_btn.setToolTip("Alle Helfer auswaehlen")
        self.all_btn.clicked.connect(self.select_all_persons)
        person_layout.addWidget(self.all_btn)
        # Die Namens-Buttons baut _refresh_person_buttons hier hinein
        self._person_layout = QVBoxLayout()
        self._person_layout.setSpacing(4)
        person_layout.addLayout(self._person_layout)
        person_layout.addStretch()
        hint = QLabel("Klick: nur diese Person\nStrg+Klick: mehrere")
        hint.setProperty("role", "muted")
        person_layout.addWidget(hint)
        person_group.setLayout(person_layout)
        layout.addWidget(person_group)

        # --- Mitte: Kalender ---
        calendar_group = QGroupBox("Kalender")
        calendar_layout = QVBoxLayout()

        stamp_layout = QHBoxLayout()
        stamp_layout.addWidget(QLabel("Eintragen:"))
        self.stamp_buttons = {}
        for stamp, label, tip in [
            (STAMP_VACATION, "Urlaub",
             "Tag anklicken: Urlaub setzen bzw. wieder entfernen."),
            (STAMP_BLOCK, "Wunsch",
             "Tag anklicken: Freiwunsch setzen bzw. wieder entfernen "
             "(die Person moechte frei haben - kein Urlaub)."),
            (STAMP_WISH, "Dienstwunsch",
             "Tag anklicken: Dienstwunsch setzen bzw. wieder entfernen "
             "(die Person moechte an dem Tag gern Dienst machen)."),
            (STAMP_CLEAR, "Loeschen",
             "Tag anklicken: Urlaub, Wunsch oder Dienstwunsch dieses Tages "
             "entfernen."),
        ]:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setToolTip(tip + " Gilt fuer alle links gewaehlten Helfer.")
            btn.toggled.connect(lambda checked, s=stamp: self.on_stamp_toggled(s, checked))
            self.stamp_buttons[stamp] = btn
            stamp_layout.addWidget(btn)

        self.hint_label = QLabel()
        self.hint_label.setProperty("role", "warning")
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
        self.calendar.cellDoubleClicked.connect(self.on_cell_double_clicked)
        self.calendar.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.calendar.verticalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        calendar_layout.addWidget(self.calendar)

        self.legend_label = QLabel()
        self.legend_label.setWordWrap(True)
        calendar_layout.addWidget(self.legend_label)
        self._update_legend()

        calendar_group.setLayout(calendar_layout)
        layout.addWidget(calendar_group, stretch=2)

        # --- Rechts: Reiter Abwesenheiten (chronologische Liste) | Notizen ---
        self.side_tabs = QTabWidget()
        list_page = QWidget()
        list_layout = QVBoxLayout()

        filter_layout = QHBoxLayout()
        self.only_month_btn = QPushButton("Nur dieser Monat")
        self.only_month_btn.setCheckable(True)
        self.only_month_btn.setToolTip(
            "Liste auf den oben gewaehlten Monat beschraenken."
        )
        self.only_month_btn.toggled.connect(self.refresh_list)
        filter_layout.addWidget(self.only_month_btn)
        self.show_past_btn = QPushButton("Vergangene anzeigen")
        self.show_past_btn.setCheckable(True)
        self.show_past_btn.setToolTip(
            "Bereits abgelaufene Abwesenheiten ein-/ausblenden."
        )
        self.show_past_btn.toggled.connect(self.refresh_list)
        filter_layout.addWidget(self.show_past_btn)
        filter_layout.addStretch()
        list_layout.addLayout(filter_layout)

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

        list_page.setLayout(list_layout)
        self.side_tabs.addTab(list_page, "Abwesenheiten/Wuensche")

        self.notes_panel = NotesPanel()
        self.notes_panel.notes_changed.connect(self._on_notes_changed)
        self.notes_panel.export_requested.connect(self.notes_export_requested.emit)
        self.side_tabs.addTab(self.notes_panel, "Notizen")
        layout.addWidget(self.side_tabs, stretch=1)

        self.setLayout(layout)

    # --- Aussenschnittstelle -------------------------------------------

    def set_plan(self, plan: MonthPlan):
        """Neuer Monatsplan: Kalender und Notizen folgen seinem Monat."""
        self.plan = plan
        self.year, self.month = plan.year, plan.month
        self.notes_panel.set_plan(plan)
        self.refresh_all()

    def refresh_all(self):
        self._refresh_person_buttons()
        self.refresh_calendar()
        self.refresh_list()
        self.notes_panel.refresh()

    def refresh_notes(self):
        """Notizen anderswo geaendert (Dienstplan-Dialog)."""
        self.notes_panel.refresh()
        self.refresh_calendar()

    def _on_notes_changed(self):
        # Notizsymbole im Kalender nachziehen und weitermelden
        self.refresh_calendar()
        self.notes_changed.emit()

    def _kind_color(self, kind: str) -> QColor:
        key = KIND_COLOR_KEYS[kind]
        return QColor(self.settings.entry_colors.get(key, DEFAULT_ENTRY_COLORS[key]))

    def _update_legend(self):
        # Farbige Kaestchen in der Legende folgen den eingestellten Farben
        swatches = "".join(
            f'<span style="background-color:{self._kind_color(kind).name()};">'
            f"&nbsp;&nbsp;&nbsp;</span> {label} &nbsp;&nbsp; "
            for kind, label in KIND_LABELS.items()
        )
        self.legend_label.setText(
            swatches
            + f"{theme.NOTE_ICON} Notiz (Doppelklick auf einen Tag) &nbsp;&nbsp; "
            "Mehrfachauswahl mit Strg/Shift, dann Rechtsklick"
        )

    # --- Helfer-Auswahl (links) ------------------------------------------

    def _refresh_person_buttons(self):
        """Ein Button je Helfer; die Auswahl bleibt erhalten (Standard: alle)."""
        if not self.plan:
            return
        while self._person_layout.count():
            widget = self._person_layout.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
        self._person_buttons = {}
        ids = [a.id for a in self.plan.assistants]
        self._selected_ids &= set(ids)
        if not self._selected_ids:
            self._selected_ids = set(ids)
        for assistant in self.plan.assistants:
            btn = QPushButton(assistant.name)
            btn.setCheckable(True)
            btn.setToolTip(
                f"Nur {assistant.name} zeigen und eintragen "
                "(Strg+Klick: zur Auswahl hinzufuegen/entfernen)"
            )
            btn.clicked.connect(
                lambda _checked=False, aid=assistant.id: self.on_person_clicked(aid)
            )
            self._person_layout.addWidget(btn)
            self._person_buttons[assistant.id] = btn
        self._sync_person_buttons()

    def _sync_person_buttons(self):
        for aid, btn in self._person_buttons.items():
            btn.setChecked(aid in self._selected_ids)
        self.all_btn.setChecked(
            bool(self._person_buttons)
            and self._selected_ids == set(self._person_buttons)
        )

    def on_person_clicked(self, assistant_id: str):
        """Klick: nur diese Person. Strg+Klick: zur Auswahl hinzufuegen bzw.
        herausnehmen (mindestens eine Person bleibt gewaehlt)."""
        ctrl = QApplication.keyboardModifiers() & Qt.KeyboardModifier.ControlModifier
        if ctrl:
            if assistant_id in self._selected_ids:
                if len(self._selected_ids) > 1:
                    self._selected_ids.discard(assistant_id)
            else:
                self._selected_ids.add(assistant_id)
        else:
            self._selected_ids = {assistant_id}
        self._on_selection_changed()

    def select_all_persons(self):
        if self.plan:
            self._selected_ids = {a.id for a in self.plan.assistants}
        self._on_selection_changed()

    def _on_selection_changed(self):
        self._sync_person_buttons()
        self.refresh_calendar()
        self.refresh_list()

    def _selected_assistants(self) -> list[Assistant]:
        """Die links gewaehlten Helfer in Team-Reihenfolge."""
        if not self.plan:
            return []
        return [a for a in self.plan.assistants if a.id in self._selected_ids]

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
        """Bei mehreren gewaehlten Helfern daran erinnern, dass ein Stempel
        fuer alle gilt."""
        count = len(self._selected_ids)
        if self.active_stamp is not None and count > 1:
            self.hint_label.setText(f"Eintragen fuer {count} Helfer gleichzeitig")
        else:
            self.hint_label.setText("")

    def on_cell_clicked(self, row: int, col: int):
        item = self.calendar.item(row, col)
        day = item.data(Qt.ItemDataRole.UserRole) if item else None
        if day is None:
            return
        if self.active_stamp is None:
            # Ohne Stempel: Tag im Notizen-Reiter mitwaehlen
            self.notes_panel.select_day(day)
            return
        self.apply_stamp(self.active_stamp, [day], self._selected_assistants())

    def on_cell_double_clicked(self, row: int, col: int):
        """Doppelklick (ohne Stempel): Notiz des Tages bearbeiten."""
        if self.active_stamp is not None:
            return
        item = self.calendar.item(row, col)
        day = item.data(Qt.ItemDataRole.UserRole) if item else None
        if day is None:
            return
        self.side_tabs.setCurrentWidget(self.notes_panel)
        self.notes_panel.select_day(day, focus=True)

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
        assistants = self._selected_assistants()
        if not days or not assistants:
            return

        who = assistants[0].name if len(assistants) == 1 else f"{len(assistants)} Helfer"
        count = f"{len(days)} Tage, " if len(days) > 1 else ""
        suffix = f" ({count}{who})"
        menu = QMenu()
        for kind, label in KIND_LABELS.items():
            menu.addAction(
                f"{label} setzen{suffix}",
                lambda _checked=False, k=kind:
                self.apply_stamp(k, days, assistants, toggle=False),
            )
        menu.addSeparator()
        menu.addAction(
            f"Eintrag entfernen{suffix}",
            lambda: self.apply_stamp(STAMP_CLEAR, days, assistants),
        )
        menu.exec(self.calendar.mapToGlobal(pos))

    def apply_stamp(self, stamp: str, days: list[int], assistants: list[Assistant],
                    toggle: bool = True):
        """Setzt/entfernt Urlaub, Wunsch oder Dienstwunsch an den Tagen
        dieses Monats - fuer alle uebergebenen (links gewaehlten) Helfer.

        toggle=True (Klick): haben alle den Tag schon, wird er bei allen
        entfernt, sonst bei allen gesetzt. toggle=False (Kontextmenue): setzt
        fuer alle Tage der Auswahl. Die Tagesarten schliessen sich
        gegenseitig aus.
        """
        if not assistants:
            return
        # Tagesmengen je Helfer und Art - erst am Ende zurueckschreiben
        sets = {
            a.id: {kind: get_days(a.constraints)
                   for kind, (get_days, _set) in DAY_KINDS.items()}
            for a in assistants
        }
        changed = False

        for day in days:
            d = date(self.year, self.month, day)
            if stamp == STAMP_CLEAR:
                for per_kind in sets.values():
                    for day_set in per_kind.values():
                        if d in day_set:
                            day_set.discard(d)
                            changed = True
                continue

            if all(d in per_kind[stamp] for per_kind in sets.values()):
                if toggle:
                    for per_kind in sets.values():
                        per_kind[stamp].discard(d)
                    changed = True
                continue
            for per_kind in sets.values():
                if d not in per_kind[stamp]:
                    per_kind[stamp].add(d)
                    for other, day_set in per_kind.items():
                        if other != stamp:
                            day_set.discard(d)
                    changed = True

        if not changed:
            return

        # Zusammenhaengende Tage werden dabei zu Zeitraeumen zusammengefasst
        for assistant in assistants:
            for kind, (_get, set_days) in DAY_KINDS.items():
                set_days(assistant.constraints, sets[assistant.id][kind])
        self.refresh_calendar()
        self.refresh_list()
        self.absences_changed.emit()

    # --- Kalender -------------------------------------------------------

    def _day_state(self, day: int) -> tuple[QColor | None, list[str]]:
        """Farbe und Beschriftungszeilen fuer einen Tag.

        Eine gewaehlte Person: deren Zustand. Mehrere: alle gewaehlten
        Helfer mit Eintrag an diesem Tag (U/W/D vor dem Namen).
        """
        d = date(self.year, self.month, day)
        persons = self._selected_assistants()
        if len(persons) == 1:
            kind = day_kind(persons[0].constraints, d)
            if kind is None:
                return None, []
            return self._kind_color(kind), [KIND_LABELS[kind]]

        lines, kinds = [], set()
        for assistant in persons:
            kind = day_kind(assistant.constraints, d)
            if kind is not None:
                lines.append(f"{KIND_SHORT[kind]} {assistant.name}")
                kinds.add(kind)
        if not lines:
            return None, []
        if len(kinds) > 1:
            # Verschiedene Arten gemischt: neutral
            color = QColor(theme.colors().separator)
        else:
            color = self._kind_color(kinds.pop())
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
        scheme = theme.colors()

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
                    item.setBackground(QColor(scheme.outside))
                else:
                    color, lines = self._day_state(day)
                    holiday = holiday_name(self.year, self.month, day)
                    note = (self.plan.notes.get(day) or "").strip()
                    item.setData(Qt.ItemDataRole.UserRole, day)
                    head = f"{day}  {theme.NOTE_ICON}" if note else str(day)
                    item.setText("\n".join([head] + lines))
                    item.setFont(small)
                    if color is not None:
                        item.setBackground(color)
                        item.setForeground(theme.text_on(color))
                    elif weekday >= 5 or holiday is not None:
                        # Feiertage grau wie Wochenenden (reine Anzeige)
                        item.setBackground(QColor(scheme.weekend))
                    tooltip = [holiday] if holiday else []
                    if note:
                        tooltip.append(f"{theme.NOTE_ICON} {note}")
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
        """Alle Eintraege aller Helfer als (start, end, assistant, kind),
        chronologisch: Zeitraeume und Einzeltage, Urlaub ("urlaub"), Wunsch
        ("block") und Dienstwunsch ("wish")."""
        absences = []
        for assistant in self.plan.assistants:
            for kind in DAY_KINDS:
                singles, ranges = _kind_lists(assistant, kind)
                for start, end in ranges:
                    absences.append((start, end, assistant, kind))
                for d in singles:
                    absences.append((d, d, assistant, kind))
        absences.sort(key=lambda v: (v[0], v[1], v[2].name))
        return absences

    def refresh_list(self):
        """Liste: gefiltert auf die links gewaehlten Helfer, optional Monat
        und Vergangenes (Eintraege des angezeigten Monats sind immer zu
        sehen, auch wenn er schon vorbei ist). Ein gewaehlter Eintrag bleibt
        gewaehlt."""
        if not self.plan:
            return
        current = self.absence_list.currentItem()
        current_key = current.data(Qt.ItemDataRole.UserRole) if current else None
        self.absence_list.blockSignals(True)
        self.absence_list.clear()

        only_month = self.only_month_btn.isChecked()
        show_past = self.show_past_btn.isChecked()
        today = date.today()
        month_start = date(self.year, self.month, 1)
        month_end = date(
            self.year, self.month, calendar.monthrange(self.year, self.month)[1]
        )

        for start, end, assistant, kind in self._all_absences():
            if assistant.id not in self._selected_ids:
                continue
            if only_month and (end < month_start or start > month_end):
                continue
            if not show_past and end < today and end < month_start:
                continue

            if start == end:
                text = "{:%d.%m.%Y}   {}".format(start, assistant.name)
            else:
                text = "{:%d.%m.%Y} - {:%d.%m.%Y}   {}".format(start, end, assistant.name)
            if kind != "urlaub":
                text += f"   [{KIND_LABELS[kind]}]"
            item = QListWidgetItem(text)
            key = (assistant.id, start.isoformat(), end.isoformat(), kind)
            item.setData(Qt.ItemDataRole.UserRole, key)
            self.absence_list.addItem(item)
            if key == current_key:
                self.absence_list.setCurrentItem(item)
        self.absence_list.blockSignals(False)

    def on_list_selection(self):
        """Eintrag in einem anderen Monat: alle Tabs wechseln dorthin."""
        item = self.absence_list.currentItem()
        if item is None:
            return
        _, start_iso, _, _ = item.data(Qt.ItemDataRole.UserRole)
        start = date.fromisoformat(start_iso)
        if (start.year, start.month) != (self.year, self.month):
            # Erst nach dem Signal wechseln: der Monatswechsel baut die
            # Liste neu auf, waehrend Qt noch in ihrem Auswahl-Signal steckt
            QTimer.singleShot(
                0, lambda: self.month_change_requested.emit(start.year, start.month)
            )

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
            assistant_combo.addItem(assistant.name, assistant.id)
        selected = self._selected_assistants()
        preset = assistant_id if assistant_id is not None else (
            selected[0].id if len(selected) == 1 else None
        )
        if preset is not None:
            index = assistant_combo.findData(preset)
            if index >= 0:
                assistant_combo.setCurrentIndex(index)
        h0.addWidget(assistant_combo)
        h0.addWidget(QLabel("Art:"))
        kind_combo = QComboBox()
        for kind_key, kind_label in KIND_LABELS.items():
            kind_combo.addItem(kind_label, kind_key)
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
        days = []
        d = start
        while d <= end:
            days.append(d)
            d += timedelta(days=1)
        # Ein Tag hat nur eine Art: aus den anderen Arten verschwindet er
        set_day_kind(assistant.constraints, days, kind)

    def _remove_absence(self, assistant: Assistant, start: date, end: date, kind: str):
        """Entfernt einen Listeneintrag: Einzeltag oder Zeitraum."""
        if assistant is None:
            return
        singles, ranges = _kind_lists(assistant, kind)
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
