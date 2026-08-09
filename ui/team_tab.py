from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QMessageBox, QColorDialog, QHeaderView,
    QGroupBox, QListWidget, QListWidgetItem, QDialog, QComboBox,
    QDateEdit, QLabel
)
from PySide6.QtCore import Qt, QSize, Signal, QDate
from PySide6.QtGui import QColor, QPixmap

from models import Assistant, AssistantConstraints, MonthPlan
from datetime import date
import uuid

from .widgets.color_button import ColorButton
from .constraints_dialog import ConstraintsDialog


class TeamTab(QWidget):
    assistants_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.plan: MonthPlan | None = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # Buttons
        button_layout = QHBoxLayout()
        self.add_btn = QPushButton("+ Helfer hinzufuegen")
        self.add_btn.clicked.connect(self.add_assistant)
        button_layout.addWidget(self.add_btn)

        self.remove_btn = QPushButton("- Entfernen")
        self.remove_btn.clicked.connect(self.remove_assistant)
        button_layout.addWidget(self.remove_btn)

        self.edit_constraints_btn = QPushButton("Einschraenkungen bearbeiten")
        self.edit_constraints_btn.clicked.connect(self.edit_constraints)
        button_layout.addWidget(self.edit_constraints_btn)

        button_layout.addStretch()
        layout.addLayout(button_layout)

        # Tabelle
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            ["Farbe", "Name", "Ziel-Dienste", "Max. Folge", "Min. Block"]
        )
        self.table.doubleClicked.connect(self.on_double_click)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

        # Urlaubsuebersicht: alle Urlaube chronologisch sortiert
        vacation_group = QGroupBox("Urlaube (chronologisch)")
        vacation_layout = QVBoxLayout()
        self.vacation_list = QListWidget()
        vacation_layout.addWidget(self.vacation_list)

        vacation_buttons = QHBoxLayout()
        self.vacation_add_btn = QPushButton("+ Urlaub hinzufuegen")
        self.vacation_add_btn.clicked.connect(self.add_vacation)
        vacation_buttons.addWidget(self.vacation_add_btn)
        self.vacation_remove_btn = QPushButton("- Entfernen")
        self.vacation_remove_btn.clicked.connect(self.remove_vacation)
        vacation_buttons.addWidget(self.vacation_remove_btn)
        vacation_buttons.addStretch()
        vacation_layout.addLayout(vacation_buttons)

        vacation_group.setLayout(vacation_layout)
        layout.addWidget(vacation_group)

        self.setLayout(layout)

    def set_plan(self, plan: MonthPlan):
        self.plan = plan
        self.refresh_table()
        self.refresh_vacations()

    def refresh_vacations(self):
        """Alle Urlaubszeitraeume aller Helfer, chronologisch nach Beginn."""
        self.vacation_list.clear()
        if not self.plan:
            return

        vacations = []
        for assistant in self.plan.assistants:
            for start, end in assistant.constraints.vacation_ranges:
                vacations.append((start, end, assistant))
        vacations.sort(key=lambda v: (v[0], v[1]))

        for start, end, assistant in vacations:
            text = "{:%d.%m.%Y} - {:%d.%m.%Y}   {}".format(start, end, assistant.name)
            item = QListWidgetItem(text)
            item.setData(
                Qt.ItemDataRole.UserRole,
                (assistant.id, start.isoformat(), end.isoformat()),
            )
            # Farbpunkt des Helfers als Markierung
            pixmap = QPixmap(12, 12)
            pixmap.fill(QColor(assistant.color))
            item.setIcon(pixmap)
            self.vacation_list.addItem(item)

    def add_vacation(self):
        if not self.plan or not self.plan.assistants:
            QMessageBox.warning(self, "Warnung", "Bitte zuerst Helfer anlegen.")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Urlaub hinzufuegen")
        layout = QVBoxLayout()

        h0 = QHBoxLayout()
        h0.addWidget(QLabel("Helfer:"))
        assistant_combo = QComboBox()
        for assistant in self.plan.assistants:
            pixmap = QPixmap(12, 12)
            pixmap.fill(QColor(assistant.color))
            assistant_combo.addItem(pixmap, assistant.name, assistant.id)
        h0.addWidget(assistant_combo)
        h0.addStretch()
        layout.addLayout(h0)

        default_date = QDate(self.plan.year, self.plan.month, 1)
        h1 = QHBoxLayout()
        h1.addWidget(QLabel("Von:"))
        start_edit = QDateEdit(default_date)
        start_edit.setCalendarPopup(True)
        h1.addWidget(start_edit)
        h1.addWidget(QLabel("Bis:"))
        end_edit = QDateEdit(default_date)
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
            return

        start = start_edit.date().toPython()
        end = end_edit.date().toPython()
        if start > end:
            QMessageBox.warning(self, "Fehler", "Startdatum muss vor dem Enddatum liegen.")
            return

        assistant_id = assistant_combo.currentData()
        assistant = next(a for a in self.plan.assistants if a.id == assistant_id)
        assistant.constraints.vacation_ranges.append((start, end))
        self.refresh_vacations()
        self.assistants_changed.emit()

    def remove_vacation(self):
        item = self.vacation_list.currentItem()
        if not item:
            QMessageBox.warning(self, "Warnung", "Bitte waehlen Sie einen Urlaub aus.")
            return

        assistant_id, start_iso, end_iso = item.data(Qt.ItemDataRole.UserRole)
        target = (date.fromisoformat(start_iso), date.fromisoformat(end_iso))
        for assistant in self.plan.assistants:
            if assistant.id == assistant_id and target in assistant.constraints.vacation_ranges:
                assistant.constraints.vacation_ranges.remove(target)
                break
        self.refresh_vacations()
        self.assistants_changed.emit()

    def refresh_table(self):
        if not self.plan:
            return

        self.table.setRowCount(len(self.plan.assistants))
        for i, assistant in enumerate(self.plan.assistants):
            # Farbe
            color_btn = ColorButton(assistant.color)
            color_btn.color_changed.connect(
                lambda new_color, idx=i: self.update_assistant_color(idx, new_color)
            )
            self.table.setCellWidget(i, 0, color_btn)

            # Name
            name_item = QTableWidgetItem(assistant.name)
            self.table.setItem(i, 1, name_item)

            # Ziel-Dienste
            target = assistant.constraints.target_shifts
            target_text = "Auto" if target is None else str(target)
            target_item = QTableWidgetItem(target_text)
            target_item.setFlags(target_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(i, 2, target_item)

            # Max. Folge
            max_consecutive = str(assistant.constraints.max_consecutive_days)
            max_item = QTableWidgetItem(max_consecutive)
            max_item.setFlags(max_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(i, 3, max_item)

            # Min. Block (Helfer mit weiter Anreise kommen am Stueck)
            min_block = str(assistant.constraints.min_block_days)
            min_item = QTableWidgetItem(min_block)
            min_item.setFlags(min_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(i, 4, min_item)

        # Button-Status
        self.add_btn.setEnabled(len(self.plan.assistants) < 10)

    def add_assistant(self):
        if not self.plan or len(self.plan.assistants) >= 10:
            return

        self._save_names_from_table()

        new_id = str(uuid.uuid4())[:8]
        constraints = AssistantConstraints(
            assistant_id=new_id,
            unavailable_dates=[],
            vacation_ranges=[],
            max_consecutive_days=3,
            target_shifts=None,
        )
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
        self.assistants_changed.emit()

    def update_assistant_color(self, row: int, color: str):
        if self.plan and 0 <= row < len(self.plan.assistants):
            self.plan.assistants[row].color = color
            self.assistants_changed.emit()

    def edit_constraints(self):
        if not self.plan:
            return

        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Warnung", "Bitte waehlen Sie einen Helfer aus.")
            return

        assistant = self.plan.assistants[row]
        dialog = ConstraintsDialog(
            assistant, self.plan.year, self.plan.month, parent=self
        )
        if dialog.exec():
            self.refresh_table()
            self.refresh_vacations()
            self.assistants_changed.emit()

    def _save_names_from_table(self):
        if not self.plan:
            return
        for i in range(self.table.rowCount()):
            name_item = self.table.item(i, 1)
            if name_item and i < len(self.plan.assistants):
                self.plan.assistants[i].name = name_item.text()

    def on_double_click(self, index):
        if index.column() == 1:  # Name-Spalte
            self._save_names_from_table()
            self.edit_constraints()
