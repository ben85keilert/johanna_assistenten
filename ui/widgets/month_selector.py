from PySide6.QtWidgets import QWidget, QHBoxLayout, QComboBox, QLabel
from PySide6.QtCore import Signal, Qt
from datetime import datetime


class MonthSelector(QWidget):
    month_changed = Signal(int, int)  # year, month

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QHBoxLayout()

        layout.addWidget(QLabel("Jahr:"))
        self.year_combo = QComboBox()
        current_year = datetime.now().year
        for y in range(current_year - 2, current_year + 3):
            self.year_combo.addItem(str(y), y)
        self.year_combo.setCurrentText(str(current_year))
        self.year_combo.currentIndexChanged.connect(self._on_changed)
        layout.addWidget(self.year_combo)

        layout.addWidget(QLabel("Monat:"))
        self.month_combo = QComboBox()
        months = [
            "Januar", "Februar", "Maerz", "April", "Mai", "Juni",
            "Juli", "August", "September", "Oktober", "November", "Dezember"
        ]
        for i, month_name in enumerate(months, 1):
            self.month_combo.addItem(month_name, i)
        current_month = datetime.now().month
        self.month_combo.setCurrentIndex(current_month - 1)
        self.month_combo.currentIndexChanged.connect(self._on_changed)
        layout.addWidget(self.month_combo)

        layout.addStretch()
        self.setLayout(layout)

    def _on_changed(self):
        year = self.year_combo.currentData()
        month = self.month_combo.currentData()
        self.month_changed.emit(year, month)

    def set_month(self, year: int, month: int):
        self.year_combo.blockSignals(True)
        self.month_combo.blockSignals(True)

        self.year_combo.setCurrentText(str(year))
        self.month_combo.setCurrentIndex(month - 1)

        self.year_combo.blockSignals(False)
        self.month_combo.blockSignals(False)
