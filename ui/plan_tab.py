from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QLabel, QSpinBox, QCheckBox, QMessageBox,
    QHeaderView, QMenu, QAbstractItemView, QButtonGroup, QComboBox,
    QGroupBox
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont

from models import MonthPlan, ShiftEntry, ShiftType, absence_days, set_absence_days
from persistence import AppSettings
from datetime import date
import calendar
import math
from . import theme
from .widgets.month_selector import MonthSelector
from .widgets.big_stepper import BigStepper
from .cell_delegate import CellDelegate
from scheduling.engine import generate
from scheduling.validator import validate

# Stempel-Modi
STAMP_FULL = "full"
STAMP_VM = "vm"
STAMP_NM = "nm"
STAMP_VACATION = "vacation"
STAMP_LOCK = "lock"

STAMP_SHIFTS = {
    STAMP_FULL: ShiftType.FULL,
    STAMP_VM: ShiftType.HALF_MORNING,
    STAMP_NM: ShiftType.HALF_AFTERNOON,
}

WEEKDAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]

# Feste Spalten vor den Tagesspalten: Soll + Belegt
DAY_COL_OFFSET = 2


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
        self._target_spins = {}  # assistant_id -> QSpinBox
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
            (STAMP_VACATION, "Urlaub"),
            (STAMP_LOCK, "Fixieren"),
        ]:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.toggled.connect(
                lambda checked, s=stamp: self.on_stamp_toggled(s, checked)
            )
            self.stamp_group.addButton(btn)
            self.stamp_buttons[stamp] = btn
            stamp_layout.addWidget(btn)

        self.confirm_check = QCheckBox("Nachfragen")
        self.confirm_check.setToolTip("Beim Ueberschreiben vorhandener Eintraege nachfragen")
        self.confirm_check.setChecked(self.settings.confirm_overwrite)
        self.confirm_check.toggled.connect(self.on_confirm_toggled)
        stamp_layout.addWidget(self.confirm_check)
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
        self.reset_btn.setToolTip("Loescht alle nicht fixierten Eintraege.")
        self.reset_btn.clicked.connect(self.reset_schedule)
        dice_layout.addWidget(self.reset_btn)

        dice_layout.addWidget(QLabel("Seed:"))
        self.seed_spin = QSpinBox()
        self.seed_spin.setRange(0, 999999)
        self.seed_spin.setValue(self.settings.seed)
        self.seed_spin.valueChanged.connect(self.on_seed_changed)
        dice_layout.addWidget(self.seed_spin)

        self.deterministic_check = QCheckBox("Deterministisch")
        self.deterministic_check.setChecked(self.settings.deterministic)
        self.deterministic_check.setToolTip(
            "An: gleicher Seed + gleiche Fixpunkte ergeben immer denselben Plan "
            "(reproduzierbar). Aus: jeder Klick auf Neu wuerfeln wuerfelt anders."
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
        self.delegate = CellDelegate(lambda: self.plan)
        self.table.setItemDelegate(self.delegate)
        layout.addWidget(self.table)

        # Zusammenfassung + Warnungen
        self.summary_label = QLabel()
        layout.addWidget(self.summary_label)
        self.warnings_label = QLabel()
        self.warnings_label.setWordWrap(True)
        self.warnings_label.setStyleSheet("color: #B05000;")
        layout.addWidget(self.warnings_label)

        self.setLayout(layout)

    # --- Einstellungen ---

    def on_confirm_toggled(self, checked: bool):
        self.settings.confirm_overwrite = checked

    def on_seed_changed(self, value: int):
        self.settings.seed = value

    def on_deterministic_toggled(self, checked: bool):
        self.settings.deterministic = checked

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
        if ref:
            self.apply_stamp(self.active_stamp, [ref])

    def _confirm(self, message: str) -> bool:
        if not self.settings.confirm_overwrite:
            return True
        reply = QMessageBox.question(
            self, "Ueberschreiben?", message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

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
        self.plan.schedule.setdefault(day, []).append(
            ShiftEntry(assistant_id=assistant_id, shift_type=shift_type)
        )

    def apply_stamp(self, stamp: str, cells: list[tuple[str, int]]):
        """Wendet einen Stempel auf Zellen (assistant_id, day) an. Gleicher
        Eintrag -> entfernen, anderer Eintrag -> nach Rueckfrage ueberschreiben."""
        if not self.plan:
            return

        # Rueckfrage gesammelt fuer alle betroffenen Zellen
        to_overwrite = 0
        for assistant_id, day in cells:
            entry = self._entry_at(assistant_id, day)
            if stamp in STAMP_SHIFTS and entry and entry.shift_type != STAMP_SHIFTS[stamp]:
                to_overwrite += 1
            if stamp == STAMP_VACATION and entry:
                to_overwrite += 1
        if to_overwrite and not self._confirm(
            f"{to_overwrite} vorhandene(n) Eintrag/Eintraege ueberschreiben?"
        ):
            return

        changed = False
        for assistant_id, day in cells:
            assistant = self._assistant_by_id.get(assistant_id)
            if assistant is None:
                continue
            entry = self._entry_at(assistant_id, day)

            if stamp in STAMP_SHIFTS:
                shift_type = STAMP_SHIFTS[stamp]
                if entry and entry.shift_type == shift_type:
                    self._remove_entry(assistant_id, day)
                else:
                    self._set_entry(assistant_id, day, shift_type)
                changed = True

            elif stamp == STAMP_VACATION:
                d = date(self.plan.year, self.plan.month, day)
                days = absence_days(assistant.constraints)
                if d in days:
                    days.discard(d)
                else:
                    if entry:
                        self._remove_entry(assistant_id, day)
                    days.add(d)
                # Zusammenhaengende Tage werden automatisch zu
                # Urlaubszeitraeumen (Team-Tab) zusammengefasst
                set_absence_days(assistant.constraints, days)
                changed = True

            elif stamp == STAMP_LOCK:
                if entry:
                    entry.locked = not entry.locked
                    changed = True

        if changed:
            self.refresh_display()
            self.plan_modified.emit()
            if stamp == STAMP_VACATION:
                self.constraints_changed.emit()

    # --- Plan/Anzeige ---

    def set_plan(self, plan: MonthPlan):
        self.plan = plan
        self.month_selector.set_month(plan.year, plan.month)
        self.rebuild_grid()

    def _day_header(self, day: int) -> str:
        weekday = WEEKDAYS[date(self.plan.year, self.plan.month, day).weekday()]
        return f"{day}\n{weekday}"

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

    def _make_target_stepper(self, assistant) -> BigStepper:
        target = assistant.constraints.target_shifts
        stepper = BigStepper(
            label=f"{assistant.name}: Soll-Dienste",
            value=-1 if target is None else target,
            minimum=-1,
            maximum=31,
            special_min_text="Auto",
        )
        stepper.setToolTip("Soll-Dienste diesen Monat (Auto = gleichmaessig verteilen)")
        stepper.value_changed.connect(
            lambda value, aid=assistant.id: self.on_target_changed(aid, value)
        )
        return stepper

    def on_target_changed(self, assistant_id: str, value: int):
        assistant = self._assistant_by_id.get(assistant_id)
        if not assistant:
            return
        assistant.constraints.target_shifts = None if value < 0 else value
        self.update_summary()
        self.plan_modified.emit()
        self.constraints_changed.emit()

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

        self.table.clear()
        self.table.setColumnCount(DAY_COL_OFFSET + half)
        self.table.setRowCount(n * 2 + 1 if split else n)

        # Spaltenkoepfe: feste Spalten + Tage der ersten Haelfte
        header_labels = ["Soll", "Belegt\nV|VM|NM"]
        for day in range(1, half + 1):
            header_labels.append(self._day_header(day))
        self.table.setHorizontalHeaderLabels(header_labels)

        # Zeilenkoepfe: Helfernamen (bei geteilter Ansicht zweimal)
        row_labels = [a.name for a in assistants]
        if split:
            row_labels += [""] + [a.name for a in assistants]
        self.table.setVerticalHeaderLabels(row_labels)

        separator_bg = QColor(215, 215, 215)

        self.table.verticalHeader().setDefaultSectionSize(theme.ROW_HEIGHT)

        # Erste Haelfte (bzw. ganzer Monat)
        for row, assistant in enumerate(assistants):
            stepper = self._make_target_stepper(assistant)
            self._target_spins[assistant.id] = stepper
            self.table.setCellWidget(row, 0, stepper)
            counts_item = self._make_inert_item()
            counts_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 1, counts_item)
            for col in range(DAY_COL_OFFSET, DAY_COL_OFFSET + half):
                day = col - DAY_COL_OFFSET + 1
                self.table.setItem(row, col, self._make_day_item(assistant.id, day))

        if split:
            # Trennzeile mit den Tageskoepfen der zweiten Haelfte
            sep_row = n
            bold = QFont()
            bold.setBold(True)
            for col in range(self.table.columnCount()):
                day = col - DAY_COL_OFFSET + 1 + half
                item = self._make_inert_item(separator_bg)
                if col >= DAY_COL_OFFSET and day <= days_in_month:
                    item.setText(self._day_header(day).replace("\n", " "))
                    item.setFont(bold)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(sep_row, col, item)

            # Zweite Haelfte
            for i, assistant in enumerate(assistants):
                row = n + 1 + i
                self.table.setItem(row, 0, self._make_inert_item())
                self.table.setItem(row, 1, self._make_inert_item())
                for col in range(DAY_COL_OFFSET, DAY_COL_OFFSET + half):
                    day = col - DAY_COL_OFFSET + 1 + half
                    if day <= days_in_month:
                        self.table.setItem(row, col, self._make_day_item(assistant.id, day))
                    else:
                        self.table.setItem(row, col, self._make_inert_item(separator_bg))

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 2 * theme.STEPPER_BUTTON_W + 64)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.refresh_display()

    def _shift_counts(self, assistant_id: str) -> tuple[int, int, int]:
        full = vm = nm = 0
        for entries in self.plan.schedule.values():
            for e in entries:
                if e.assistant_id != assistant_id:
                    continue
                if e.shift_type == ShiftType.FULL:
                    full += 1
                elif e.shift_type == ShiftType.HALF_MORNING:
                    vm += 1
                else:
                    nm += 1
        return full, vm, nm

    def refresh_display(self):
        if not self.plan:
            return
        # Belegt-Spalte (nur obere Zeilengruppe)
        for row, assistant in enumerate(self.plan.assistants):
            item = self.table.item(row, 1)
            if item:
                full, vm, nm = self._shift_counts(assistant.id)
                item.setText(f"{full} | {vm} | {nm}")
        # Der Delegate zeichnet die Tageszellen direkt aus den Plandaten
        self.table.viewport().update()
        self.update_summary()

    def update_summary(self):
        if not self.plan:
            return

        summary_parts = []
        for assistant in self.plan.assistants:
            full, vm, nm = self._shift_counts(assistant.id)
            target = assistant.constraints.target_shifts
            target_text = f" Soll {target}" if target is not None else ""
            summary_parts.append(f"{assistant.name} ({full}|{vm}|{nm}){target_text}")
        legend = "Legende: Name (VOLL|VM|NM)"
        self.summary_label.setText("   ".join(summary_parts) + "      " + legend)

        warnings = validate(self.plan)
        self.warnings_label.setText("\n".join(w.message for w in warnings))

    # --- Generieren ---

    def generate_schedule(self):
        if not self.plan:
            return

        seed = self.settings.seed if self.settings.deterministic else None
        try:
            self.plan = generate(self.plan, seed)
            self.plan.seed = seed
            self.refresh_display()
            self.plan_modified.emit()
        except Exception as e:
            QMessageBox.critical(self, "Fehler", f"Generierung fehlgeschlagen:\n{e}")

    def reset_schedule(self):
        if not self.plan:
            return
        reply = QMessageBox.question(
            self, "Zuruecksetzen",
            "Alle nicht fixierten Eintraege loeschen?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        for day in list(self.plan.schedule.keys()):
            self.plan.schedule[day] = [e for e in self.plan.schedule[day] if e.locked]
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
        menu.addAction("Loeschen" + suffix, lambda: self.delete_cells(cells))
        menu.addSeparator()
        menu.addAction("Urlaub setzen/entfernen" + suffix,
                       lambda: self.apply_stamp(STAMP_VACATION, cells))
        menu.addSeparator()
        menu.addAction("Fixieren" + suffix, lambda: self.set_locked(cells, True))
        menu.addAction("Fixierung loesen" + suffix, lambda: self.set_locked(cells, False))

        menu.exec(self.table.mapToGlobal(pos))

    def delete_cells(self, cells: list[tuple[str, int]]):
        if not self.plan:
            return
        existing = [
            (assistant_id, day) for assistant_id, day in cells
            if self._entry_at(assistant_id, day)
        ]
        if not existing:
            return
        if not self._confirm(f"{len(existing)} Eintrag/Eintraege loeschen?"):
            return
        for assistant_id, day in existing:
            self._remove_entry(assistant_id, day)
        self.refresh_display()
        self.plan_modified.emit()

    def set_locked(self, cells: list[tuple[str, int]], locked: bool):
        if not self.plan:
            return
        changed = False
        for assistant_id, day in cells:
            entry = self._entry_at(assistant_id, day)
            if entry and entry.locked != locked:
                entry.locked = locked
                changed = True
        if changed:
            self.refresh_display()
            self.plan_modified.emit()
