from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QCalendarWidget,
    QListWidget, QListWidgetItem, QPushButton, QLabel, QSpinBox,
    QCheckBox, QDateEdit, QMessageBox
)
from PySide6.QtCore import Qt, QDate
from datetime import date, datetime

from models import Assistant


class ConstraintsDialog(QDialog):
    def __init__(self, assistant: Assistant, year: int, month: int, parent=None):
        super().__init__(parent)
        self.assistant = assistant
        self.year = year
        self.month = month
        self.setWindowTitle(f"Einschraenkungen - {assistant.name}")
        self.setGeometry(200, 200, 600, 700)
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout()

        # Abschnitt 1: Nicht verfuegbar (Einzeltage)
        group1 = QGroupBox("Nicht verfuegbar (Einzeltage)")
        layout1 = QVBoxLayout()
        self.calendar = QCalendarWidget()
        self.calendar.setSelectedDate(QDate(self.year, self.month, 1))
        self.calendar.clicked.connect(self.toggle_unavailable_date)
        layout1.addWidget(self.calendar)
        group1.setLayout(layout1)
        main_layout.addWidget(group1)

        # Abschnitt 2: Urlaub (Zeitraeume)
        group2 = QGroupBox("Urlaub (Zeitraeume)")
        layout2 = QVBoxLayout()
        self.vacation_list = QListWidget()
        self.refresh_vacation_list()
        layout2.addWidget(self.vacation_list)

        vacation_buttons = QHBoxLayout()
        self.vacation_add_btn = QPushButton("Hinzufuegen")
        self.vacation_add_btn.clicked.connect(self.add_vacation)
        vacation_buttons.addWidget(self.vacation_add_btn)

        self.vacation_remove_btn = QPushButton("Entfernen")
        self.vacation_remove_btn.clicked.connect(self.remove_vacation)
        vacation_buttons.addWidget(self.vacation_remove_btn)

        vacation_buttons.addStretch()
        layout2.addLayout(vacation_buttons)
        group2.setLayout(layout2)
        main_layout.addWidget(group2)

        # Abschnitt 3: Einschraenkungen
        group3 = QGroupBox("Einschraenkungen")
        layout3 = QVBoxLayout()

        # Max. aufeinanderfolgende Tage
        h1 = QHBoxLayout()
        h1.addWidget(QLabel("Max. aufeinanderfolgende Tage:"))
        self.max_consecutive_spin = QSpinBox()
        self.max_consecutive_spin.setRange(1, 3)
        self.max_consecutive_spin.setValue(
            self.assistant.constraints.max_consecutive_days
        )
        h1.addWidget(self.max_consecutive_spin)
        h1.addStretch()
        layout3.addLayout(h1)

        # Ziel-Dienste
        h2 = QHBoxLayout()
        h2.addWidget(QLabel("Ziel-Dienste diesen Monat:"))
        self.target_auto_check = QCheckBox("Auto")
        self.target_auto_check.setChecked(
            self.assistant.constraints.target_shifts is None
        )
        self.target_auto_check.stateChanged.connect(self.on_auto_toggle)
        h2.addWidget(self.target_auto_check)

        self.target_spin = QSpinBox()
        self.target_spin.setRange(0, 31)
        if self.assistant.constraints.target_shifts is not None:
            self.target_spin.setValue(self.assistant.constraints.target_shifts)
        self.target_spin.setEnabled(
            self.assistant.constraints.target_shifts is not None
        )
        h2.addWidget(self.target_spin)
        h2.addStretch()
        layout3.addLayout(h2)

        group3.setLayout(layout3)
        main_layout.addWidget(group3)

        # Buttons
        button_layout = QHBoxLayout()
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.save_and_close)
        cancel_btn = QPushButton("Abbrechen")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addStretch()
        button_layout.addWidget(ok_btn)
        button_layout.addWidget(cancel_btn)
        main_layout.addLayout(button_layout)

        self.setLayout(main_layout)
        self.highlight_unavailable_dates()

    def toggle_unavailable_date(self, date_obj: QDate):
        date_py = date(date_obj.year(), date_obj.month(), date_obj.day())
        constraints = self.assistant.constraints
        if date_py in constraints.unavailable_dates:
            constraints.unavailable_dates.remove(date_py)
        else:
            constraints.unavailable_dates.append(date_py)
        self.highlight_unavailable_dates()

    def highlight_unavailable_dates(self):
        from PySide6.QtGui import QTextCharFormat, QColor

        fmt = QTextCharFormat()
        fmt.setBackground(QColor(255, 200, 200))

        for day in self.assistant.constraints.unavailable_dates:
            if day.year == self.year and day.month == self.month:
                q_date = QDate(day.year, day.month, day.day)
                self.calendar.setDateTextFormat(q_date, fmt)

    def refresh_vacation_list(self):
        self.vacation_list.clear()
        for start, end in self.assistant.constraints.vacation_ranges:
            text = "{}.{:02d}.{} - {}.{:02d}.{}".format(
                start.day, start.month, start.year,
                end.day, end.month, end.year
            )
            self.vacation_list.addItem(text)

    def add_vacation(self):
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel

        dialog = QDialog(self)
        dialog.setWindowTitle("Urlaubszeitraum hinzufuegen")
        layout = QVBoxLayout()

        h1 = QHBoxLayout()
        h1.addWidget(QLabel("Von:"))
        start_edit = QDateEdit()
        start_edit.setDate(QDate(self.year, self.month, 1))
        h1.addWidget(start_edit)
        layout.addLayout(h1)

        h2 = QHBoxLayout()
        h2.addWidget(QLabel("Bis:"))
        end_edit = QDateEdit()
        end_edit.setDate(QDate(self.year, self.month, 1))
        h2.addWidget(end_edit)
        layout.addLayout(h2)

        button_layout = QHBoxLayout()
        ok_btn = QPushButton("OK")
        cancel_btn = QPushButton("Abbrechen")
        button_layout.addStretch()
        button_layout.addWidget(ok_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

        dialog.setLayout(layout)

        ok_btn.clicked.connect(dialog.accept)
        cancel_btn.clicked.connect(dialog.reject)

        if dialog.exec():
            start_date = date(
                start_edit.date().year(),
                start_edit.date().month(),
                start_edit.date().day()
            )
            end_date = date(
                end_edit.date().year(),
                end_edit.date().month(),
                end_edit.date().day()
            )
            if start_date <= end_date:
                self.assistant.constraints.vacation_ranges.append((start_date, end_date))
                self.refresh_vacation_list()
            else:
                QMessageBox.warning(
                    self,
                    "Fehler",
                    "Startdatum muss vor dem Enddatum liegen."
                )

    def remove_vacation(self):
        row = self.vacation_list.currentRow()
        if row >= 0:
            del self.assistant.constraints.vacation_ranges[row]
            self.refresh_vacation_list()

    def on_auto_toggle(self):
        is_auto = self.target_auto_check.isChecked()
        self.target_spin.setEnabled(not is_auto)

    def save_and_close(self):
        self.assistant.constraints.max_consecutive_days = (
            self.max_consecutive_spin.value()
        )
        if self.target_auto_check.isChecked():
            self.assistant.constraints.target_shifts = None
        else:
            self.assistant.constraints.target_shifts = self.target_spin.value()
        self.accept()
