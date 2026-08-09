from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel, QFrame
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
import shiboken6

from . import theme
from .widgets.big_stepper import BigStepper


class ControlBar(QFrame):
    """Zentrale Werte-Steuerleiste unter dem Menue.

    Zeigt das zuletzt angeklickte Wertefeld (BigStepper) und aendert dessen
    Wert mit uebertrieben grossen Rauf/Runter-Buttons. Mit den Pfeil-Buttons
    links/rechts springt man zum vorherigen/naechsten Wertefeld des aktiven
    Tabs, ohne die kleinen Felder treffen zu muessen.
    """

    def __init__(self, targets_provider, parent=None):
        super().__init__(parent)
        # callable() -> geordnete Liste aller BigStepper im aktiven Tab
        self.targets_provider = targets_provider
        self._target: BigStepper | None = None

        self.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QHBoxLayout()
        layout.setContentsMargins(8, 4, 8, 4)

        big_font = QFont()
        big_font.setPointSize(theme.CONTROL_BAR_FONT_PT)
        big_font.setBold(True)

        def make_button(text: str, handler, autorepeat: bool = False) -> QPushButton:
            btn = QPushButton(text)
            btn.setFixedSize(theme.CONTROL_BAR_BUTTON_W, theme.CONTROL_BAR_BUTTON_H)
            btn.setFont(big_font)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            if autorepeat:
                btn.setAutoRepeat(True)
                btn.setAutoRepeatDelay(400)
                btn.setAutoRepeatInterval(180)
            btn.clicked.connect(handler)
            return btn

        self.prev_btn = make_button("◀", lambda: self._navigate(-1))
        self.prev_btn.setToolTip("Vorheriges Wertefeld")
        layout.addWidget(self.prev_btn)

        self.next_btn = make_button("▶", lambda: self._navigate(1))
        self.next_btn.setToolTip("Naechstes Wertefeld")
        layout.addWidget(self.next_btn)

        self.info_label = QLabel()
        self.info_label.setFont(big_font)
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.info_label, stretch=1)

        self.down_btn = make_button("▼", lambda: self._step(-1), autorepeat=True)
        self.down_btn.setToolTip("Wert verkleinern")
        layout.addWidget(self.down_btn)

        self.up_btn = make_button("▲", lambda: self._step(1), autorepeat=True)
        self.up_btn.setToolTip("Wert vergroessern")
        layout.addWidget(self.up_btn)

        self.setLayout(layout)
        self._refresh()

    # --- Ziel-Verwaltung ---

    def _target_valid(self) -> bool:
        return self._target is not None and shiboken6.isValid(self._target)

    def set_target(self, stepper: BigStepper):
        if self._target is stepper:
            self._refresh()
            return
        if self._target_valid():
            try:
                self._target.value_changed.disconnect(self._refresh)
            except RuntimeError:
                pass
        self._target = stepper
        if stepper is not None:
            stepper.value_changed.connect(self._refresh)
        self._refresh()

    def _refresh(self, *_):
        if self._target_valid():
            self.info_label.setText(
                f"{self._target.label_text}:  {self._target.display_text()}"
            )
        else:
            self._target = None
            self.info_label.setText("Wertefeld anklicken oder ◀ ▶ nutzen")
        enabled = self._target_valid()
        self.up_btn.setEnabled(enabled)
        self.down_btn.setEnabled(enabled)

    # --- Aktionen ---

    def _step(self, delta: int):
        if self._target_valid():
            self._target.step(delta)
            self._refresh()

    def _navigate(self, direction: int):
        targets = [t for t in self.targets_provider() if shiboken6.isValid(t)]
        if not targets:
            self.set_target(None)
            return
        if self._target_valid() and self._target in targets:
            index = (targets.index(self._target) + direction) % len(targets)
        else:
            index = 0 if direction >= 0 else len(targets) - 1
        self.set_target(targets[index])
