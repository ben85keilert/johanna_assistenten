from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel
from PySide6.QtCore import Qt, Signal

from .. import theme


class BigStepper(QWidget):
    """Werteingabe mit grossen, nebeneinander liegenden Minus/Plus-Buttons.

    Ersetzt QSpinBox ueberall dort, wo die winzigen Auf/Ab-Pfeile schwer zu
    treffen sind. Die Buttons wiederholen beim Gedrueckthalten automatisch.
    Ueber `activate_hook` meldet sich das zuletzt benutzte Feld bei der
    zentralen Steuerleiste (ControlBar) an.
    """

    value_changed = Signal(int)

    # Wird von MainWindow gesetzt: callable(stepper) -> None
    activate_hook = None

    def __init__(self, label: str, value: int, minimum: int, maximum: int,
                 special_min_text: str | None = None, parent=None):
        super().__init__(parent)
        self.label_text = label
        self._minimum = minimum
        self._maximum = maximum
        self._special_min_text = special_min_text
        self._value = max(minimum, min(maximum, value))

        layout = QHBoxLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(2)

        self.minus_btn = QPushButton("−")
        self.plus_btn = QPushButton("+")
        for btn in (self.minus_btn, self.plus_btn):
            btn.setFixedSize(theme.STEPPER_BUTTON_W, theme.STEPPER_BUTTON_H)
            btn.setAutoRepeat(True)
            btn.setAutoRepeatDelay(400)
            btn.setAutoRepeatInterval(180)

        self.value_label = QLabel()
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.value_label.setMinimumWidth(theme.STEPPER_VALUE_W)

        self.minus_btn.clicked.connect(lambda: self.step(-1))
        self.plus_btn.clicked.connect(lambda: self.step(1))

        layout.addWidget(self.minus_btn)
        layout.addWidget(self.value_label)
        layout.addWidget(self.plus_btn)
        self.setLayout(layout)
        self._update_display()

    def value(self) -> int:
        return self._value

    def set_value(self, value: int, emit: bool = False):
        value = max(self._minimum, min(self._maximum, value))
        if value == self._value:
            return
        self._value = value
        self._update_display()
        if emit:
            self.value_changed.emit(self._value)

    def step(self, delta: int):
        self._activate()
        new_value = max(self._minimum, min(self._maximum, self._value + delta))
        if new_value != self._value:
            self._value = new_value
            self._update_display()
            self.value_changed.emit(self._value)

    def display_text(self) -> str:
        if self._special_min_text is not None and self._value == self._minimum:
            return self._special_min_text
        return str(self._value)

    def _update_display(self):
        self.value_label.setText(self.display_text())
        self.minus_btn.setEnabled(self._value > self._minimum)
        self.plus_btn.setEnabled(self._value < self._maximum)

    def _activate(self):
        if BigStepper.activate_hook is not None:
            BigStepper.activate_hook(self)

    def mousePressEvent(self, event):
        self._activate()
        super().mousePressEvent(event)
