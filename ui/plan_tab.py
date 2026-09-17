from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QLabel, QSpinBox, QCheckBox, QMessageBox,
    QHeaderView, QMenu, QAbstractItemView, QButtonGroup, QComboBox,
    QGroupBox, QDialog, QPlainTextEdit
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont

from models import (
    MonthPlan, ShiftEntry, ShiftType, is_effective,
    absence_days, set_absence_days, blocked_days, set_blocked_days,
    holiday_name,
)
from persistence import AppSettings
from datetime import date
import calendar
import math
import random
from . import theme
from .widgets.month_selector import MonthSelector
from .widgets.big_stepper import BigStepper
from .cell_delegate import CellDelegate
from .conflict_dialog import ConflictDialog
from scheduling.engine import generate
from scheduling.validator import validate

# Stempel-Modi
STAMP_FULL = "full"
STAMP_VM = "vm"
STAMP_NM = "nm"
STAMP_ONCALL = "oncall"
STAMP_VACATION = "vacation"
STAMP_BLOCK = "block"
STAMP_NOTE = "note"
STAMP_LOCK = "lock"
STAMP_DELETE = "delete"

# Notizsymbol im Tageskopf, wenn eine Notiz vorhanden ist (zentral im Theme,
# der CellDelegate nutzt dasselbe Symbol in den Zellen)
NOTE_ICON = theme.NOTE_ICON

STAMP_SHIFTS = {
    STAMP_FULL: ShiftType.FULL,
    STAMP_VM: ShiftType.HALF_MORNING,
    STAMP_NM: ShiftType.HALF_AFTERNOON,
    STAMP_ONCALL: ShiftType.ON_CALL,
}

# Dienstarten mit Kandidaten-Mechanik: mehrere manuelle Vorschlaege je Tag,
# aus denen gewaehlt wird (VM/NM bleiben Ausnahme-Dienste ohne Kandidaten)
CANDIDATE_TYPES = (ShiftType.FULL, ShiftType.ON_CALL)

WEEKDAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]

# Feste Spalten vor den Tagesspalten: Soll Min + Soll Max + Belegt
DAY_COL_OFFSET = 3

# Hintergrund der grauen Kopf-Zeilen in der geteilten Ansicht
SEPARATOR_BG = QColor(215, 215, 215)


class PlanTab(QWidget):
    plan_modified = Signal()
    # Einschraenkungen (Soll-Dienste, Urlaube) geaendert -> Team-Tab aktualisieren
    constraints_changed = Signal()
    month_change_requested = Signal(int, int)  # year, month

    def __init__(self, settings: AppSettings, parent=None):
        super().__init__(parent)
        self.plan: MonthPlan | None = None
        self.settings = settings
        self.active_stamp: str | None = None
        self._assistant_by_id = {}
        self._target_spins = {}  # (assistant_id, "min"|"max") -> BigStepper
        self._group1_row_offset = 0
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # Monatswahl + Ansichtsumschaltung: wird von MainWindow neben die
        # Tab-Reiter gesetzt (Ecke der Tab-Leiste), nicht ins eigene Layout
        self.top_bar = QWidget()
        top_layout = QHBoxLayout()
        top_layout.setContentsMargins(0, 0, 8, 0)
        self.month_selector = MonthSelector()
        self.month_selector.layout().setContentsMargins(0, 0, 0, 0)
        self.month_selector.month_changed.connect(self.month_change_requested.emit)
        top_layout.addWidget(self.month_selector)

        top_layout.addWidget(QLabel("Ansicht:"))
        self.view_combo = QComboBox()
        self.view_combo.addItem("Breit (eine Zeile)", False)
        self.view_combo.addItem("Zweigeteilt (untereinander)", True)
        self.view_combo.setCurrentIndex(1 if self.settings.split_view else 0)
        self.view_combo.currentIndexChanged.connect(self.on_view_changed)
        top_layout.addWidget(self.view_combo)
        self.top_bar.setLayout(top_layout)

        # Eine Werkzeugzeile: zwei umrandete Gruppen (Stempel | Wuerfeln)
        tools_layout = QHBoxLayout()

        stamp_box = QGroupBox("Stempel")
        stamp_layout = QHBoxLayout()
        self.stamp_group = QButtonGroup(self)
        self.stamp_group.setExclusive(False)
        self.stamp_buttons = {}
        for stamp, label in [
            (STAMP_FULL, "Tagesdienst"),
            (STAMP_VM, "VM"),
            (STAMP_NM, "NM"),
            (STAMP_ONCALL, "Rufbereitschaft"),
            (STAMP_VACATION, "Urlaub"),
            (STAMP_BLOCK, "Block"),
            (STAMP_NOTE, "Notiz"),
            (STAMP_LOCK, "Fixieren"),
            (STAMP_DELETE, "Loeschen"),
        ]:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.toggled.connect(
                lambda checked, s=stamp: self.on_stamp_toggled(s, checked)
            )
            self.stamp_group.addButton(btn)
            self.stamp_buttons[stamp] = btn
            stamp_layout.addWidget(btn)

        self.overwrite_check = QCheckBox("Ueberschreiben")
        self.overwrite_check.setToolTip(
            "An: Stempel duerfen vorhandene Eintraege anderen Typs ersetzen. "
            "Aus (Standard): nur leere Zellen stempeln bzw. gleiche Stempel "
            "wieder entfernen."
        )
        self.overwrite_check.setChecked(self.settings.allow_overwrite)
        self.overwrite_check.toggled.connect(self.on_overwrite_toggled)
        stamp_layout.addWidget(self.overwrite_check)
        stamp_box.setLayout(stamp_layout)
        tools_layout.addWidget(stamp_box)

        dice_box = QGroupBox("Wuerfeln")
        dice_layout = QHBoxLayout()

        self.generate_btn = QPushButton("Neu wuerfeln")
        self.generate_btn.setToolTip(
            "Fuellt freie Tage zufaellig. Manuell Gesetztes und Fixiertes "
            "bleibt stehen, nicht fixierte Zufalls-Eintraege werden neu vergeben."
        )
        self.generate_btn.clicked.connect(self.generate_schedule)
        dice_layout.addWidget(self.generate_btn)

        self.reset_btn = QPushButton("Zuruecksetzen")
        self.reset_btn.setToolTip(
            "Loescht alle nicht fixierten Zufalls-Eintraege. "
            "Manuell Gesetztes (auch Kandidaten) bleibt stehen."
        )
        self.reset_btn.clicked.connect(self.reset_schedule)
        dice_layout.addWidget(self.reset_btn)

        self.seed_label = QLabel("Seed:")
        dice_layout.addWidget(self.seed_label)
        self.seed_spin = QSpinBox()
        self.seed_spin.setRange(0, 999999)
        self.seed_spin.setValue(self.settings.seed)
        self.seed_spin.valueChanged.connect(self.on_seed_changed)
        # Ohne Deterministisch hat der Seed keine Wirkung -> ausgrauen
        self.seed_spin.setEnabled(self.settings.deterministic)
        self.seed_label.setEnabled(self.settings.deterministic)
        dice_layout.addWidget(self.seed_spin)

        self.deterministic_check = QCheckBox("Deterministisch")
        self.deterministic_check.setChecked(self.settings.deterministic)
        self.deterministic_check.setToolTip(
            "An: gleicher Seed + gleiche Fixpunkte ergeben immer denselben Plan "
            "(reproduzierbar). Aus: jeder Klick auf Neu wuerfeln anders."
        )
        self.deterministic_check.toggled.connect(self.on_deterministic_toggled)
        dice_layout.addWidget(self.deterministic_check)
        dice_box.setLayout(dice_layout)
        tools_layout.addWidget(dice_box)

        tools_layout.addStretch()
        layout.addLayout(tools_layout)

        # Tabelle
        self.table = QTableWidget()
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        self.table.cellClicked.connect(self.on_cell_clicked)
        self.table.itemSelectionChanged.connect(self._update_note_line)
        self.delegate = CellDelegate(lambda: self.plan, self.settings)
        self.table.setItemDelegate(self.delegate)
        layout.addWidget(self.table)

        # Notizzeile: zeigt die Notiz des zuletzt angeklickten Tages
        self.note_label = QLabel()
        self.note_label.setWordWrap(True)
        self.note_label.setStyleSheet("color: #555555;")
        layout.addWidget(self.note_label)

        # Zusammenfassung + Warnungen
        self.summary_label = QLabel()
        layout.addWidget(self.summary_label)
        self.warnings_label = QLabel()
        self.warnings_label.setWordWrap(True)
        self.warnings_label.setStyleSheet("color: #B05000;")
        layout.addWidget(self.warnings_label)

        self.setLayout(layout)

    # --- Einstellungen ---

    def on_overwrite_toggled(self, checked: bool):
        self.settings.allow_overwrite = checked

    def on_seed_changed(self, value: int):
        self.settings.seed = value

    def on_deterministic_toggled(self, checked: bool):
        self.settings.deterministic = checked
        self.seed_spin.setEnabled(checked)
        self.seed_label.setEnabled(checked)

    def on_view_changed(self):
        self.settings.split_view = bool(self.view_combo.currentData())
        self.rebuild_grid()

    # --- Stempel ---

    def on_stamp_toggled(self, stamp: str, checked: bool):
        if checked:
            # Exklusiv, aber abwaehlbar: andere Stempel deaktivieren
            for other, btn in self.stamp_buttons.items():
                if other != stamp and btn.isChecked():
                    btn.setChecked(False)
            self.active_stamp = stamp
        elif self.active_stamp == stamp:
            self.active_stamp = None

    def _cell_ref(self, row: int, col: int) -> tuple[str, int] | None:
        item = self.table.item(row, col)
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def on_cell_clicked(self, row: int, col: int):
        if not self.plan or self.active_stamp is None:
            return
        ref = self._cell_ref(row, col)
        if not ref:
            return
        if self.active_stamp == STAMP_NOTE:
            # Notiz gilt fuer den Tag, nicht fuer die einzelne Zelle
            self.edit_note(ref[1])
            return
        self.apply_stamp(self.active_stamp, [ref])

    def _entry_at(self, assistant_id: str, day: int) -> ShiftEntry | None:
        return next(
            (e for e in self.plan.schedule.get(day, []) if e.assistant_id == assistant_id),
            None,
        )

    def _remove_entry(self, assistant_id: str, day: int):
        entries = self.plan.schedule.get(day, [])
        self.plan.schedule[day] = [e for e in entries if e.assistant_id != assistant_id]
        if not self.plan.schedule[day]:
            del self.plan.schedule[day]

    def _set_entry(self, assistant_id: str, day: int, shift_type: ShiftType):
        self._remove_entry(assistant_id, day)
        # Gestempelte Dienste sind automatisch fixiert (Fixpunkte)
        self.plan.schedule.setdefault(day, []).append(
            ShiftEntry(assistant_id=assistant_id, shift_type=shift_type, locked=True)
        )

    # --- Kandidaten (mehrere Personen fuer denselben Dienst/RB am Tag) ---

    def _same_type_manual_entries(self, day: int, shift_type: ShiftType,
                                  exclude_id: str | None = None) -> list[ShiftEntry]:
        """Manuelle Eintraege (inkl. Kandidaten) dieses Typs anderer Personen."""
        return [
            e for e in self.plan.schedule.get(day, [])
            if e.shift_type == shift_type and not e.generated
            and e.assistant_id != exclude_id
        ]

    def _normalize_candidates(self, day: int, shift_type: ShiftType):
        """Bleibt nur ein Kandidat uebrig, wird er wieder ein normaler
        fixer Einzeleintrag (ein manueller Volleintrag = fix)."""
        candidates = [
            e for e in self.plan.schedule.get(day, [])
            if e.candidate and e.shift_type == shift_type
        ]
        if len(candidates) == 1:
            e = candidates[0]
            e.candidate = False
            e.chosen = False
            e.locked = True

    def _choose_candidate_entry(self, entry: ShiftEntry, day: int):
        """Feste Wahl eines Kandidaten: uebrige Kandidaten desselben
        Tags/Typs verlieren ihre Wahl."""
        for e in self.plan.schedule.get(day, []):
            if e.candidate and e.shift_type == entry.shift_type and e is not entry:
                e.chosen = False
                e.locked = False
        entry.chosen = True
        entry.locked = True

    def choose_candidate(self, assistant_id: str, day: int):
        entry = self._entry_at(assistant_id, day)
        if not self.plan or entry is None or not entry.candidate:
            return
        self._choose_candidate_entry(entry, day)
        self.refresh_display()
        self.plan_modified.emit()

    def apply_stamp(self, stamp: str, cells: list[tuple[str, int]]):
        """Wendet einen Stempel auf Zellen (assistant_id, day) an.

        Gleicher Eintrag -> entfernen (Toggle), leere Zelle -> setzen.
        Eintraege anderen Typs werden nur ersetzt, wenn "Ueberschreiben"
        eingeschaltet ist - sonst passiert nichts.
        """
        if not self.plan:
            return
        allow_overwrite = self.settings.allow_overwrite

        changed = False
        for assistant_id, day in cells:
            assistant = self._assistant_by_id.get(assistant_id)
            if assistant is None:
                continue
            entry = self._entry_at(assistant_id, day)

            if stamp == STAMP_DELETE:
                # Entfernt Stempel und Zufalls-Vorschlaege
                if entry:
                    self._remove_entry(assistant_id, day)
                    if entry.candidate:
                        self._normalize_candidates(day, entry.shift_type)
                    changed = True

            elif stamp in STAMP_SHIFTS:
                shift_type = STAMP_SHIFTS[stamp]
                if entry and entry.shift_type == shift_type:
                    self._remove_entry(assistant_id, day)
                    # Verbleibt genau ein Kandidat, wird er wieder fix
                    self._normalize_candidates(day, shift_type)
                elif entry is None or allow_overwrite:
                    if entry is not None:
                        self._remove_entry(assistant_id, day)
                    others = (
                        self._same_type_manual_entries(day, shift_type, assistant_id)
                        if shift_type in CANDIDATE_TYPES else []
                    )
                    if others:
                        # Zweite/weitere Person fuer denselben Dienst/RB:
                        # alle manuellen Eintraege des Typs werden Kandidaten
                        # - der Tag ist damit wieder "zu waehlen"
                        for e in others:
                            e.candidate = True
                            e.chosen = False
                            e.locked = False
                        self.plan.schedule.setdefault(day, []).append(
                            ShiftEntry(
                                assistant_id=assistant_id,
                                shift_type=shift_type,
                                candidate=True,
                            )
                        )
                    else:
                        self._set_entry(assistant_id, day, shift_type)
                else:
                    continue
                changed = True

            elif stamp in (STAMP_VACATION, STAMP_BLOCK):
                d = date(self.plan.year, self.plan.month, day)
                if stamp == STAMP_VACATION:
                    get_days, set_days = absence_days, set_absence_days
                    other_get, other_set = blocked_days, set_blocked_days
                else:
                    get_days, set_days = blocked_days, set_blocked_days
                    other_get, other_set = absence_days, set_absence_days
                days = get_days(assistant.constraints)
                if d in days:
                    days.discard(d)
                else:
                    other_days = other_get(assistant.constraints)
                    if entry is not None or d in other_days:
                        if not allow_overwrite:
                            continue
                        if entry is not None:
                            self._remove_entry(assistant_id, day)
                        if d in other_days:
                            other_days.discard(d)
                            other_set(assistant.constraints, other_days)
                    days.add(d)
                # Zusammenhaengende Tage werden automatisch zu
                # Zeitraeumen (Team-Tab) zusammengefasst
                set_days(assistant.constraints, days)
                changed = True

            elif stamp == STAMP_LOCK:
                if entry:
                    if entry.candidate and not entry.locked:
                        # Fixieren eines Kandidaten = feste Wahl
                        self._choose_candidate_entry(entry, day)
                    else:
                        entry.locked = not entry.locked
                    changed = True

        if changed:
            self.refresh_display()
            self.plan_modified.emit()
            if stamp in (STAMP_VACATION, STAMP_BLOCK):
                self.constraints_changed.emit()

    # --- Plan/Anzeige ---

    def set_plan(self, plan: MonthPlan):
        self.plan = plan
        self.month_selector.set_month(plan.year, plan.month)
        self.rebuild_grid()

    def _note_text(self, day: int) -> str:
        if not self.plan:
            return ""
        return (self.plan.notes.get(day) or "").strip()

    def _day_header(self, day: int) -> str:
        weekday = WEEKDAYS[date(self.plan.year, self.plan.month, day).weekday()]
        # Tage mit Notiz tragen das Notizsymbol im Kopf
        icon = f" {NOTE_ICON}" if self._note_text(day) else ""
        return f"{day}{icon}\n{weekday}"

    def _day_header_tooltip(self, day: int) -> str:
        """Tooltip des Tageskopfs: Feiertagsname und/oder Notiz."""
        holiday = holiday_name(self.plan.year, self.plan.month, day)
        return "\n\n".join(filter(None, [holiday, self._note_text(day)]))

    def _make_day_item(self, assistant_id: str, day: int) -> QTableWidgetItem:
        item = QTableWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, (assistant_id, day))
        return item

    def _make_inert_item(self, background: QColor | None = None) -> QTableWidgetItem:
        item = QTableWidgetItem()
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        if background:
            item.setBackground(background)
        return item

    def _make_target_stepper(self, assistant, field: str) -> BigStepper:
        if field == "min":
            target = assistant.constraints.min_shifts
            label = "Min. Dienste"
            tooltip = "Mindestens so viele Dienste diesen Monat (Auto = keine Untergrenze)"
        else:
            target = assistant.constraints.max_shifts
            label = "Max. Dienste"
            tooltip = "Hoechstens so viele Dienste diesen Monat (Auto = gleichmaessig verteilen)"
        stepper = BigStepper(
            label=f"{assistant.name}: {label}",
            value=-1 if target is None else target,
            minimum=-1,
            maximum=31,
            special_min_text="Auto",
        )
        stepper.setToolTip(tooltip)
        stepper.value_changed.connect(
            lambda value, aid=assistant.id, f=field: self.on_target_changed(aid, f, value)
        )
        return stepper

    def on_target_changed(self, assistant_id: str, field: str, value: int):
        assistant = self._assistant_by_id.get(assistant_id)
        if not assistant:
            return
        c = assistant.constraints
        new_value = None if value < 0 else value
        if field == "min":
            c.min_shifts = new_value
            # Max mitziehen; "Auto" (None) clampt nie
            if new_value is not None and c.max_shifts is not None and c.max_shifts < new_value:
                c.max_shifts = new_value
                other = self._target_spins.get((assistant_id, "max"))
                if other:
                    other.set_value(new_value)
        else:
            c.max_shifts = new_value
            if new_value is not None and c.min_shifts is not None and c.min_shifts > new_value:
                c.min_shifts = new_value
                other = self._target_spins.get((assistant_id, "min"))
                if other:
                    other.set_value(new_value)
        self.update_summary()
        self.plan_modified.emit()
        self.constraints_changed.emit()

    def _fill_day_header_row(self, row: int, first_day: int, days_in_month: int):
        """Graue Kopf-Zeile im Tabellenkoerper: einzeilig fett "1 Sa", "2 So"…"""
        bold = QFont()
        bold.setBold(True)
        for col in range(self.table.columnCount()):
            day = col - DAY_COL_OFFSET + first_day
            item = self._make_inert_item(SEPARATOR_BG)
            if col >= DAY_COL_OFFSET and day <= days_in_month:
                item.setText(self._day_header(day).replace("\n", " "))
                item.setFont(bold)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                tooltip = self._day_header_tooltip(day)
                if tooltip:
                    item.setToolTip(tooltip)
            self.table.setItem(row, col, item)

    def rebuild_grid(self):
        if not self.plan:
            return

        year, month = self.plan.year, self.plan.month
        days_in_month = calendar.monthrange(year, month)[1]
        assistants = self.plan.assistants
        n = len(assistants)
        self._assistant_by_id = {a.id: a for a in assistants}
        self._target_spins = {}

        split = self.settings.split_view
        half = math.ceil(days_in_month / 2) if split else days_in_month
        # Bei geteilter Ansicht bekommt jede Haelfte eine eigene graue
        # Kopf-Zeile im Tabellenkoerper; Gruppe 1 beginnt dann bei Zeile 1
        self._group1_row_offset = 1 if split else 0

        self.table.clear()
        self.table.setColumnCount(DAY_COL_OFFSET + half)
        self.table.setRowCount(n * 2 + 2 if split else n)

        # Spaltenkoepfe: feste Spalten; Tages-Labels nur in der breiten
        # Ansicht (geteilt uebernehmen das die grauen Kopf-Zeilen).
        # Max steht links von Min: Max begrenzt Min, also wird es zuerst
        # eingestellt (sonst zieht ein spaeter gesetztes Max das Min zurueck)
        header_labels = ["Soll\nMax", "Soll\nMin", "Belegt\nV|VM|NM|RB"]
        for day in range(1, half + 1):
            header_labels.append("" if split else self._day_header(day))
        self.table.setHorizontalHeaderLabels(header_labels)

        # Zeilenkoepfe: Helfernamen (bei geteilter Ansicht zweimal)
        row_labels = [a.name for a in assistants]
        if split:
            row_labels = [""] + row_labels + [""] + [a.name for a in assistants]
        self.table.setVerticalHeaderLabels(row_labels)

        self.table.verticalHeader().setDefaultSectionSize(theme.ROW_HEIGHT)

        off = self._group1_row_offset
        if split:
            self._fill_day_header_row(0, first_day=1, days_in_month=days_in_month)

        # Erste Haelfte (bzw. ganzer Monat)
        for i, assistant in enumerate(assistants):
            row = off + i
            for col, field in ((0, "max"), (1, "min")):
                stepper = self._make_target_stepper(assistant, field)
                self._target_spins[(assistant.id, field)] = stepper
                self.table.setCellWidget(row, col, stepper)
            counts_item = self._make_inert_item()
            counts_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 2, counts_item)
            for col in range(DAY_COL_OFFSET, DAY_COL_OFFSET + half):
                day = col - DAY_COL_OFFSET + 1
                self.table.setItem(row, col, self._make_day_item(assistant.id, day))

        if split:
            # Kopf-Zeile der zweiten Haelfte
            self._fill_day_header_row(off + n, first_day=half + 1, days_in_month=days_in_month)

            # Zweite Haelfte
            for i, assistant in enumerate(assistants):
                row = off + n + 1 + i
                for col in range(DAY_COL_OFFSET):
                    self.table.setItem(row, col, self._make_inert_item())
                for col in range(DAY_COL_OFFSET, DAY_COL_OFFSET + half):
                    day = col - DAY_COL_OFFSET + 1 + half
                    if day <= days_in_month:
                        self.table.setItem(row, col, self._make_day_item(assistant.id, day))
                    else:
                        self.table.setItem(row, col, self._make_inert_item(SEPARATOR_BG))

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        for col in (0, 1):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(col, theme.STEPPER_WIDTH)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.refresh_display()

    def _shift_counts(self, assistant_id: str) -> tuple[int, int, int, int]:
        full = vm = nm = rb = 0
        for entries in self.plan.schedule.values():
            for e in entries:
                # Nicht gewaehlte Kandidaten sind nur Vorschlaege
                if e.assistant_id != assistant_id or not is_effective(e):
                    continue
                if e.shift_type == ShiftType.FULL:
                    full += 1
                elif e.shift_type == ShiftType.HALF_MORNING:
                    vm += 1
                elif e.shift_type == ShiftType.HALF_AFTERNOON:
                    nm += 1
                elif e.shift_type == ShiftType.ON_CALL:
                    rb += 1
        return full, vm, nm, rb

    def refresh_display(self):
        if not self.plan:
            return
        # Belegt-Spalte (nur obere Zeilengruppe)
        off = getattr(self, "_group1_row_offset", 0)
        for i, assistant in enumerate(self.plan.assistants):
            item = self.table.item(off + i, 2)
            if item:
                full, vm, nm, rb = self._shift_counts(assistant.id)
                item.setText(f"{full} | {vm} | {nm} | {rb}")
        # Der Delegate zeichnet die Tageszellen direkt aus den Plandaten
        self.table.viewport().update()
        self._update_day_headers()
        self._update_note_line()
        self.update_summary()

    # --- Tagesnotizen ---

    def _update_day_headers(self):
        """Notizsymbol + Tooltip in den Tageskoepfen nachziehen."""
        if not self.plan:
            return
        days_in_month = calendar.monthrange(self.plan.year, self.plan.month)[1]
        if self.settings.split_view:
            half = math.ceil(days_in_month / 2)
            n = len(self.plan.assistants)
            self._fill_day_header_row(0, first_day=1, days_in_month=days_in_month)
            self._fill_day_header_row(
                self._group1_row_offset + n, first_day=half + 1,
                days_in_month=days_in_month,
            )
        else:
            for col in range(DAY_COL_OFFSET, self.table.columnCount()):
                day = col - DAY_COL_OFFSET + 1
                item = self.table.horizontalHeaderItem(col)
                if item is None or day > days_in_month:
                    continue
                item.setText(self._day_header(day))
                item.setToolTip(self._day_header_tooltip(day))

    def _current_day(self) -> int | None:
        """Tag der aktuell gewaehlten Zelle (fuer die Notizzeile)."""
        item = self.table.currentItem()
        if item is None:
            return None
        ref = item.data(Qt.ItemDataRole.UserRole)
        return ref[1] if ref else None

    def _update_note_line(self):
        if not self.plan:
            self.note_label.setText("")
            return
        day = self._current_day()
        note = self._note_text(day) if day else ""
        if note:
            self.note_label.setText(
                f"{NOTE_ICON} Notiz {day}.{self.plan.month:02d}.: {note}"
            )
        else:
            self.note_label.setText("")

    def edit_note(self, day: int):
        """Dialog zum Anlegen/Bearbeiten der Tagesnotiz.

        Leerer Text loescht die Notiz (das Symbol im Tageskopf verschwindet).
        """
        if not self.plan:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(
            f"Notiz fuer {day:02d}.{self.plan.month:02d}.{self.plan.year}"
        )
        layout = QVBoxLayout()
        editor = QPlainTextEdit(self._note_text(day))
        editor.setPlaceholderText("Notiz zu diesem Tag ...")
        editor.setMinimumSize(360, 120)
        layout.addWidget(editor)
        hint = QLabel("Leer lassen und OK druecken loescht die Notiz.")
        hint.setStyleSheet("color: #777777;")
        layout.addWidget(hint)

        buttons = QHBoxLayout()
        buttons.addStretch()
        ok_btn = QPushButton("OK")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(dialog.accept)
        buttons.addWidget(ok_btn)
        cancel_btn = QPushButton("Abbrechen")
        cancel_btn.clicked.connect(dialog.reject)
        buttons.addWidget(cancel_btn)
        layout.addLayout(buttons)
        dialog.setLayout(layout)
        editor.setFocus()

        if not dialog.exec():
            return
        text = editor.toPlainText().strip()
        if text == self._note_text(day):
            return
        if text:
            self.plan.notes[day] = text
        else:
            self.plan.notes.pop(day, None)
        self.refresh_display()
        self.plan_modified.emit()

    def update_summary(self):
        if not self.plan:
            return

        summary_parts = []
        for assistant in self.plan.assistants:
            full, vm, nm, rb = self._shift_counts(assistant.id)
            min_shifts = assistant.constraints.min_shifts
            max_shifts = assistant.constraints.max_shifts
            if min_shifts is not None and max_shifts is not None:
                target_text = f" Soll {min_shifts}-{max_shifts}"
            elif min_shifts is not None:
                target_text = f" Soll min {min_shifts}"
            elif max_shifts is not None:
                target_text = f" Soll max {max_shifts}"
            else:
                target_text = ""
            summary_parts.append(f"{assistant.name} ({full}|{vm}|{nm}|{rb}){target_text}")
        legend = "Legende: Name (VOLL|VM|NM|RB)"
        self.summary_label.setText("   ".join(summary_parts) + "      " + legend)

        warnings = validate(self.plan)
        self.warnings_label.setText("\n".join(w.message for w in warnings))

    # --- Generieren ---

    def generate_schedule(self):
        if not self.plan:
            return

        # Auch ohne "Deterministisch" einen konkreten Seed ziehen: der
        # Konflikt-Dialog wiederholt den Lauf ggf. mit denselben Wuerfeln
        if self.settings.deterministic:
            seed = self.settings.seed
        else:
            seed = random.randrange(0, 1_000_000)
        try:
            result = generate(self.plan, seed)
            self.plan = result.plan
            self.plan.seed = seed
            self.refresh_display()
            self.plan_modified.emit()
            if result.conflicts:
                self._handle_conflicts(result, seed)
        except Exception as e:
            QMessageBox.critical(self, "Fehler", f"Generierung fehlgeschlagen:\n{e}")

    def _handle_conflicts(self, result, seed: int):
        """Zeigt die Konflikte des Laufs; weicht die Nutzerwahl von den
        angewendeten Vorschlaegen ab, wiederholt sich der Lauf mit einem
        Resolver, der diese Entscheidungen beantwortet."""
        dialog = ConflictDialog(result.conflicts, self)
        if not dialog.exec():
            return  # Vorschlaege behalten
        decisions = dialog.decisions()
        applied = {
            (c.day, c.kind): c.options[c.applied].assistant_id
            for c in result.conflicts
        }
        if decisions == applied:
            return

        def resolver(conflict):
            key = (conflict.day, conflict.kind)
            if key in decisions:
                for option in conflict.options:
                    if option.assistant_id == decisions[key]:
                        return option
            return conflict.options[conflict.proposal]

        rerun = generate(self.plan, seed, resolver=resolver)
        self.plan = rerun.plan
        self.refresh_display()
        self.plan_modified.emit()

    def reset_schedule(self):
        if not self.plan:
            return
        reply = QMessageBox.question(
            self, "Zuruecksetzen",
            "Alle nicht fixierten Zufalls-Eintraege loeschen?\n"
            "Manuell gesetzte Eintraege bleiben erhalten.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        for day in list(self.plan.schedule.keys()):
            # Wie beim Neuwuerfeln: nur Zufalls-Eintraege fliegen raus,
            # manuell Gesetztes (inkl. Kandidaten) bleibt immer stehen.
            kept = [e for e in self.plan.schedule[day]
                    if e.locked or not e.generated]
            for e in kept:
                # Eine nicht fixierte Wuerfel-Wahl ist Teil des Zufalls
                if e.candidate and not e.locked:
                    e.chosen = False
            self.plan.schedule[day] = kept
            if not self.plan.schedule[day]:
                del self.plan.schedule[day]
        self.refresh_display()
        self.plan_modified.emit()

    # --- Rechtsklick / Mehrfachauswahl ---

    def _selected_cells(self, fallback_pos=None) -> list[tuple[str, int]]:
        cells = []
        for item in self.table.selectedItems():
            ref = item.data(Qt.ItemDataRole.UserRole)
            if ref:
                cells.append(ref)
        if not cells and fallback_pos is not None:
            item = self.table.itemAt(fallback_pos)
            if item:
                ref = item.data(Qt.ItemDataRole.UserRole)
                if ref:
                    cells.append(ref)
        return cells

    def show_context_menu(self, pos):
        if not self.plan:
            return
        cells = self._selected_cells(fallback_pos=pos)
        if not cells:
            return

        n = len(cells)
        suffix = f" ({n} Zellen)" if n > 1 else ""
        menu = QMenu()

        shift_menu = menu.addMenu("Dienst setzen" + suffix)
        shift_menu.addAction("Tagesdienst (VOLL)", lambda: self.apply_stamp(STAMP_FULL, cells))
        shift_menu.addAction("VM (Vormittag)", lambda: self.apply_stamp(STAMP_VM, cells))
        shift_menu.addAction("NM (Nachmittag)", lambda: self.apply_stamp(STAMP_NM, cells))
        shift_menu.addAction("Rufbereitschaft (RB)", lambda: self.apply_stamp(STAMP_ONCALL, cells))
        menu.addAction("Loeschen" + suffix, lambda: self.apply_stamp(STAMP_DELETE, cells))
        menu.addSeparator()
        menu.addAction("Urlaub setzen/entfernen" + suffix,
                       lambda: self.apply_stamp(STAMP_VACATION, cells))
        menu.addAction("Block setzen/entfernen" + suffix,
                       lambda: self.apply_stamp(STAMP_BLOCK, cells))
        menu.addSeparator()
        menu.addAction("Fixieren" + suffix, lambda: self.set_locked(cells, True))
        menu.addAction("Fixierung loesen" + suffix, lambda: self.set_locked(cells, False))

        # Notiz gilt je Tag: Tag der Zelle unter dem Mauszeiger, sonst der
        # ersten markierten Zelle
        item = self.table.itemAt(pos)
        ref = item.data(Qt.ItemDataRole.UserRole) if item else None
        note_day = ref[1] if ref else cells[0][1]

        # Feste Wahl eines Kandidaten (Zelle unter dem Mauszeiger)
        if ref:
            entry = self._entry_at(ref[0], ref[1])
            if entry is not None and entry.candidate:
                menu.addSeparator()
                menu.addAction(
                    "Kandidat fest waehlen",
                    lambda: self.choose_candidate(ref[0], ref[1]),
                )
        menu.addSeparator()
        menu.addAction(
            f"Notiz fuer Tag {note_day} bearbeiten...",
            lambda: self.edit_note(note_day),
        )

        menu.exec(self.table.mapToGlobal(pos))

    def set_locked(self, cells: list[tuple[str, int]], locked: bool):
        if not self.plan:
            return
        changed = False
        for assistant_id, day in cells:
            entry = self._entry_at(assistant_id, day)
            if entry is None:
                continue
            if locked and entry.candidate and not entry.locked:
                # Fixieren eines Kandidaten = feste Wahl
                self._choose_candidate_entry(entry, day)
                changed = True
            elif entry.locked != locked:
                entry.locked = locked
                changed = True
        if changed:
            self.refresh_display()
            self.plan_modified.emit()
