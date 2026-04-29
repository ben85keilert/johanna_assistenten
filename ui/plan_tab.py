from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QLabel, QSpinBox, QCheckBox, QMessageBox,
    QHeaderView, QMenu
)
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QColor, QFont

from models import MonthPlan, ShiftEntry, ShiftType
from datetime import date, datetime
import calendar
from .widgets.month_selector import MonthSelector
from .cell_delegate import CellDelegate
from scheduling.engine import generate


class PlanTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.plan: MonthPlan | None = None
        self.month_selector: MonthSelector | None = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # Monatswahl
        self.month_selector = MonthSelector()
        self.month_selector.month_changed.connect(self.on_month_changed)
        layout.addWidget(self.month_selector)

        # Generierungs-Optionen
        options_layout = QHBoxLayout()
        options_layout.addWidget(QLabel("Seed:"))
        self.seed_spin = QSpinBox()
        self.seed_spin.setRange(0, 999999)
        self.seed_spin.setValue(42)
        options_layout.addWidget(self.seed_spin)

        self.deterministic_check = QCheckBox("Deterministisch")
        self.deterministic_check.setChecked(True)
        options_layout.addWidget(self.deterministic_check)

        options_layout.addStretch()
        layout.addLayout(options_layout)

        # Buttons
        button_layout = QHBoxLayout()
        self.generate_btn = QPushButton("Dienstplan generieren")
        self.generate_btn.clicked.connect(self.generate_schedule)
        button_layout.addWidget(self.generate_btn)

        self.regenerate_locked_btn = QPushButton("Gesperrte behalten & Rest neu")
        self.regenerate_locked_btn.clicked.connect(self.regenerate_with_locked)
        button_layout.addWidget(self.regenerate_locked_btn)

        self.reset_btn = QPushButton("Zurücksetzen")
        self.reset_btn.clicked.connect(self.reset_schedule)
        button_layout.addWidget(self.reset_btn)

        button_layout.addStretch()
        layout.addLayout(button_layout)

        # Tabelle
        self.table = QTableWidget()
        self.table.setColumnCount(1)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        layout.addWidget(self.table)

        # Zusammenfassung
        self.summary_label = QLabel()
        layout.addWidget(self.summary_label)

        self.setLayout(layout)

    def set_plan(self, plan: MonthPlan):
        self.plan = plan
        self.month_selector.set_month(plan.year, plan.month)
        self.rebuild_grid()

    def on_month_changed(self, year: int, month: int):
        if self.plan:
            self.plan.year = year
            self.plan.month = month
            self.plan.schedule.clear()
            self.rebuild_grid()

    def rebuild_grid(self):
        if not self.plan:
            return

        year, month = self.plan.year, self.plan.month
        days_in_month = calendar.monthrange(year, month)[1]
        assistants = self.plan.assistants

        self.table.setRowCount(len(assistants))
        self.table.setColumnCount(days_in_month + 1)

        # Header: Tag + Wochentag
        header_labels = [""]
        for day in range(1, days_in_month + 1):
            d = date(year, month, day)
            weekday = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"][d.weekday()]
            header_labels.append(f"{day}\n{weekday}")
        self.table.setHorizontalHeaderLabels(header_labels)

        # Row-Header: Assistenten
        row_labels = [a.name for a in assistants]
        self.table.setVerticalHeaderLabels(row_labels)

        # Zellen füllen
        delegate = CellDelegate(self.plan)
        self.table.setItemDelegate(delegate)

        for row, assistant in enumerate(assistants):
            for col in range(days_in_month + 1):
                if col == 0:
                    item = QTableWidgetItem(assistant.name)
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.table.setItem(row, col, item)
                else:
                    day = col
                    item = QTableWidgetItem()
                    item.setData(Qt.ItemDataRole.UserRole, (assistant.id, day))
                    self.table.setItem(row, col, item)

                    # Hintergrund für Wochenende
                    d = date(year, month, col)
                    if d.weekday() >= 5:
                        item.setBackground(QColor(240, 240, 240))

        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.update_cell_display()
        self.update_summary()

    def update_cell_display(self):
        if not self.plan:
            return

        year, month = self.plan.year, self.plan.month
        for row in range(self.table.rowCount()):
            for col in range(1, self.table.columnCount()):
                day = col
                assistant_id = self.plan.assistants[row].id

                item = self.table.item(row, col)
                entries = self.plan.schedule.get(day, [])
                matching = [e for e in entries if e.assistant_id == assistant_id]

                if matching:
                    entry = matching[0]
                    if entry.shift_type == ShiftType.FULL:
                        item.setText("VOLL")
                    elif entry.shift_type == ShiftType.HALF_MORNING:
                        item.setText("VM")
                    else:
                        item.setText("NM")

                    # Farbe + Sperr-Icon werden im Delegate gezeichnet
                    item.setBackground(QColor(self.plan.assistants[row].color))
                else:
                    item.setText("")
                    if date(year, month, day).weekday() >= 5:
                        item.setBackground(QColor(240, 240, 240))
                    else:
                        item.setBackground(QColor(255, 255, 255))

    def update_summary(self):
        if not self.plan:
            return

        summary_parts = []
        for assistant in self.plan.assistants:
            count = sum(
                1 for entries in self.plan.schedule.values()
                for e in entries
                if e.assistant_id == assistant.id
            )
            summary_parts.append(f"{assistant.name}: {count}")

        self.summary_label.setText(" | ".join(summary_parts))

    def generate_schedule(self):
        if not self.plan:
            return

        seed = self.seed_spin.value() if self.deterministic_check.isChecked() else None
        try:
            self.plan = generate(self.plan, seed)
            self.plan.seed = seed
            self.update_cell_display()
            self.update_summary()
            QMessageBox.information(self, "Erfolg", "Dienstplan generiert.")
        except Exception as e:
            QMessageBox.critical(self, "Fehler", f"Generierung fehlgeschlagen:\n{e}")

    def regenerate_with_locked(self):
        if not self.plan:
            return

        seed = self.seed_spin.value() if self.deterministic_check.isChecked() else None
        try:
            self.plan = generate(self.plan, seed, respect_locked=True)
            self.plan.seed = seed
            self.update_cell_display()
            self.update_summary()
            QMessageBox.information(self, "Erfolg", "Dienstplan (mit gesperrten) aktualisiert.")
        except Exception as e:
            QMessageBox.critical(self, "Fehler", f"Generierung fehlgeschlagen:\n{e}")

    def reset_schedule(self):
        if self.plan:
            self.plan.schedule.clear()
            self.update_cell_display()
            self.update_summary()

    def show_context_menu(self, pos):
        item = self.table.itemAt(pos)
        if not item or item.column() == 0:
            return

        row = self.table.row(item)
        col = self.table.column(item)
        day = col

        assistant_id = self.plan.assistants[row].id

        menu = QMenu()

        # Dienst setzen
        shift_menu = menu.addMenu("Dienst setzen")
        shift_menu.addAction("VOLL", lambda: self.set_shift(day, assistant_id, ShiftType.FULL))
        shift_menu.addAction("VM (Morgens)", lambda: self.set_shift(day, assistant_id, ShiftType.HALF_MORNING))
        shift_menu.addAction("NM (Abends)", lambda: self.set_shift(day, assistant_id, ShiftType.HALF_AFTERNOON))
        shift_menu.addAction("Loeschen", lambda: self.set_shift(day, assistant_id, None))

        # Sperren
        entries = self.plan.schedule.get(day, [])
        matching = [e for e in entries if e.assistant_id == assistant_id]
        if matching:
            entry = matching[0]
            if entry.locked:
                menu.addAction("Entsperren", lambda: self.toggle_lock(day, assistant_id, False))
            else:
                menu.addAction("Sperren", lambda: self.toggle_lock(day, assistant_id, True))

        menu.exec(self.table.mapToGlobal(pos))

    def set_shift(self, day: int, assistant_id: str, shift_type: ShiftType | None):
        if not self.plan:
            return

        if day not in self.plan.schedule:
            self.plan.schedule[day] = []

        entries = self.plan.schedule[day]
        matching = [e for e in entries if e.assistant_id == assistant_id]

        if matching:
            entries.remove(matching[0])

        if shift_type is not None:
            entries.append(ShiftEntry(assistant_id=assistant_id, shift_type=shift_type))

        self.update_cell_display()
        self.update_summary()

    def toggle_lock(self, day: int, assistant_id: str, locked: bool):
        if not self.plan or day not in self.plan.schedule:
            return

        entries = self.plan.schedule[day]
        matching = [e for e in entries if e.assistant_id == assistant_id]
        if matching:
            matching[0].locked = locked
            self.update_cell_display()
