from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QLabel, QSpinBox, QCheckBox, QMessageBox,
    QHeaderView, QMenu, QAbstractItemView, QButtonGroup
)
from PySide6.QtCore import Qt, Signal

from models import MonthPlan, ShiftEntry, ShiftType
from persistence import AppSettings
from datetime import date
import calendar
from .widgets.month_selector import MonthSelector
from .cell_delegate import CellDelegate
from scheduling.engine import generate, shift_weight
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


class PlanTab(QWidget):
    plan_modified = Signal()
    month_change_requested = Signal(int, int)  # year, month

    def __init__(self, settings: AppSettings, parent=None):
        super().__init__(parent)
        self.plan: MonthPlan | None = None
        self.settings = settings
        self.active_stamp: str | None = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # Monatswahl
        self.month_selector = MonthSelector()
        self.month_selector.month_changed.connect(self.month_change_requested.emit)
        layout.addWidget(self.month_selector)

        # Stempel-Leiste
        stamp_layout = QHBoxLayout()
        stamp_layout.addWidget(QLabel("Stempel:"))
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

        self.confirm_check = QCheckBox("Beim Ueberschreiben nachfragen")
        self.confirm_check.setChecked(self.settings.confirm_overwrite)
        self.confirm_check.toggled.connect(self.on_confirm_toggled)
        stamp_layout.addWidget(self.confirm_check)

        stamp_layout.addStretch()
        layout.addLayout(stamp_layout)

        # Generierung
        options_layout = QHBoxLayout()

        self.generate_btn = QPushButton("Generieren / Neu wuerfeln")
        self.generate_btn.setToolTip(
            "Fuellt freie Tage zufaellig. Manuell Gesetztes und Fixiertes "
            "bleibt stehen, nicht fixierte Zufalls-Eintraege werden neu vergeben."
        )
        self.generate_btn.clicked.connect(self.generate_schedule)
        options_layout.addWidget(self.generate_btn)

        self.reset_btn = QPushButton("Zuruecksetzen")
        self.reset_btn.setToolTip("Loescht alle nicht fixierten Eintraege.")
        self.reset_btn.clicked.connect(self.reset_schedule)
        options_layout.addWidget(self.reset_btn)

        options_layout.addSpacing(20)
        options_layout.addWidget(QLabel("Seed:"))
        self.seed_spin = QSpinBox()
        self.seed_spin.setRange(0, 999999)
        self.seed_spin.setValue(self.settings.seed)
        self.seed_spin.valueChanged.connect(self.on_seed_changed)
        options_layout.addWidget(self.seed_spin)

        self.deterministic_check = QCheckBox("Deterministisch")
        self.deterministic_check.setChecked(self.settings.deterministic)
        self.deterministic_check.toggled.connect(self.on_deterministic_toggled)
        options_layout.addWidget(self.deterministic_check)

        options_layout.addStretch()
        layout.addLayout(options_layout)

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

    def on_cell_clicked(self, row: int, col: int):
        if not self.plan or self.active_stamp is None or col == 0:
            return
        self.apply_stamp(self.active_stamp, [(row, col)])

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

    def apply_stamp(self, stamp: str, cells: list[tuple[int, int]]):
        """Wendet einen Stempel auf Zellen (row, col) an. Gleicher Eintrag ->
        entfernen, anderer Eintrag -> nach Rueckfrage ueberschreiben."""
        if not self.plan:
            return

        # Rueckfrage gesammelt fuer alle betroffenen Zellen
        to_overwrite = 0
        for row, col in cells:
            assistant_id = self.plan.assistants[row].id
            entry = self._entry_at(assistant_id, col)
            if stamp in STAMP_SHIFTS and entry and entry.shift_type != STAMP_SHIFTS[stamp]:
                to_overwrite += 1
            if stamp == STAMP_VACATION and entry:
                to_overwrite += 1
        if to_overwrite and not self._confirm(
            f"{to_overwrite} vorhandene(n) Eintrag/Eintraege ueberschreiben?"
        ):
            return

        changed = False
        for row, col in cells:
            assistant = self.plan.assistants[row]
            day = col
            entry = self._entry_at(assistant.id, day)

            if stamp in STAMP_SHIFTS:
                shift_type = STAMP_SHIFTS[stamp]
                if entry and entry.shift_type == shift_type:
                    self._remove_entry(assistant.id, day)
                else:
                    self._set_entry(assistant.id, day, shift_type)
                changed = True

            elif stamp == STAMP_VACATION:
                d = date(self.plan.year, self.plan.month, day)
                unavailable = assistant.constraints.unavailable_dates
                if d in unavailable:
                    unavailable.remove(d)
                else:
                    if entry:
                        self._remove_entry(assistant.id, day)
                    unavailable.append(d)
                changed = True

            elif stamp == STAMP_LOCK:
                if entry:
                    entry.locked = not entry.locked
                    changed = True

        if changed:
            self.refresh_display()
            self.plan_modified.emit()

    # --- Plan/Anzeige ---

    def set_plan(self, plan: MonthPlan):
        self.plan = plan
        self.month_selector.set_month(plan.year, plan.month)
        self.rebuild_grid()

    def rebuild_grid(self):
        if not self.plan:
            return

        year, month = self.plan.year, self.plan.month
        days_in_month = calendar.monthrange(year, month)[1]
        assistants = self.plan.assistants

        self.table.clear()
        self.table.setRowCount(len(assistants))
        self.table.setColumnCount(days_in_month + 1)

        header_labels = [""]
        for day in range(1, days_in_month + 1):
            weekday = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"][date(year, month, day).weekday()]
            header_labels.append(f"{day}\n{weekday}")
        self.table.setHorizontalHeaderLabels(header_labels)
        self.table.setVerticalHeaderLabels([a.name for a in assistants])

        for row, assistant in enumerate(assistants):
            name_item = QTableWidgetItem(assistant.name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, name_item)
            for col in range(1, days_in_month + 1):
                item = QTableWidgetItem()
                item.setData(Qt.ItemDataRole.UserRole, (assistant.id, col))
                self.table.setItem(row, col, item)

        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.refresh_display()

    def refresh_display(self):
        # Der Delegate zeichnet direkt aus den Plandaten
        self.table.viewport().update()
        self.update_summary()

    def update_summary(self):
        if not self.plan:
            return

        summary_parts = []
        for assistant in self.plan.assistants:
            count = sum(
                shift_weight(e.shift_type)
                for entries in self.plan.schedule.values()
                for e in entries
                if e.assistant_id == assistant.id
            )
            target = assistant.constraints.target_shifts
            target_text = f"/{target}" if target is not None else ""
            summary_parts.append(f"{assistant.name}: {count:g}{target_text}")
        self.summary_label.setText(" | ".join(summary_parts))

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

    def _selected_cells(self, fallback_pos=None) -> list[tuple[int, int]]:
        cells = [
            (item.row(), item.column())
            for item in self.table.selectedItems()
            if item.column() > 0
        ]
        if not cells and fallback_pos is not None:
            item = self.table.itemAt(fallback_pos)
            if item and item.column() > 0:
                cells = [(item.row(), item.column())]
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

    def delete_cells(self, cells: list[tuple[int, int]]):
        if not self.plan:
            return
        existing = [
            (row, col) for row, col in cells
            if self._entry_at(self.plan.assistants[row].id, col)
        ]
        if not existing:
            return
        if not self._confirm(f"{len(existing)} Eintrag/Eintraege loeschen?"):
            return
        for row, col in existing:
            self._remove_entry(self.plan.assistants[row].id, col)
        self.refresh_display()
        self.plan_modified.emit()

    def set_locked(self, cells: list[tuple[int, int]], locked: bool):
        if not self.plan:
            return
        changed = False
        for row, col in cells:
            entry = self._entry_at(self.plan.assistants[row].id, col)
            if entry and entry.locked != locked:
                entry.locked = locked
                changed = True
        if changed:
            self.refresh_display()
            self.plan_modified.emit()
