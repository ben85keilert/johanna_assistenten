from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QMessageBox, QColorDialog, QHeaderView
)
from PySide6.QtCore import Qt, QSize, Signal
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
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Farbe", "Name", "Ziel-Dienste", "Max. Folge"])
        self.table.doubleClicked.connect(self.on_double_click)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

        self.setLayout(layout)

    def set_plan(self, plan: MonthPlan):
        self.plan = plan
        self.refresh_table()

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
