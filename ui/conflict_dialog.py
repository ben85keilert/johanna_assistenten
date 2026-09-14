"""Konflikt-Dialog nach dem Wuerfeln.

Konnte ein Tag nur durch Ueberplanen eines Nachrang-Freiwunschs besetzt
werden, hat der Generator bereits einen vernuenftigen Vorschlag angewendet.
Dieser Dialog zeigt alle diese Entscheidungen und laesst je Konflikt eine
andere ueberplanbare Person oder "Tag offen lassen" waehlen. Urlaube sind
zwingend und tauchen hier nie auf; Wuensche sind es nicht.
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QComboBox,
    QPushButton, QScrollArea, QWidget,
)

KIND_LABELS = {"dienst": "Dienst", "rb": "Rufbereitschaft"}


class ConflictDialog(QDialog):
    """Zeigt die Konflikte eines Generator-Laufs (scheduling.engine.Conflict).

    decisions() liefert nach exec() die Auswahl je Konflikt:
    {(day, kind): assistant_id | None} - None = Tag offen lassen.
    """

    def __init__(self, conflicts: list, parent=None):
        super().__init__(parent)
        self.conflicts = conflicts
        self._combos = {}
        self.setWindowTitle("Konflikte beim Wuerfeln")

        layout = QVBoxLayout()
        hint = QLabel(
            "An diesen Tagen war der Plan nur durch Ueberplanen eines "
            "Freiwunschs (Nachrang) zu fuellen - Urlaube sind zwingend, "
            "Wuensche nicht. Der Vorschlag ist jeweils vorausgewaehlt; "
            "hier laesst sich eine andere Person oder \"Tag offen lassen\" "
            "waehlen."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        grid = QGridLayout()
        for row, conflict in enumerate(conflicts):
            grid.addWidget(
                QLabel(f"Tag {conflict.day} — {KIND_LABELS.get(conflict.kind, conflict.kind)}:"),
                row, 0,
            )
            combo = QComboBox()
            for option in conflict.options:
                combo.addItem(option.label, option.assistant_id)
            combo.setCurrentIndex(conflict.applied)
            grid.addWidget(combo, row, 1)
            self._combos[(conflict.day, conflict.kind)] = combo
        grid.setColumnStretch(2, 1)

        # Bei vielen Konflikten scrollbar halten
        inner = QWidget()
        inner.setLayout(grid)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        layout.addWidget(scroll)

        buttons = QHBoxLayout()
        buttons.addStretch()
        ok_btn = QPushButton("Uebernehmen")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept)
        buttons.addWidget(ok_btn)
        cancel_btn = QPushButton("Vorschlaege behalten")
        cancel_btn.setToolTip(
            "Schliesst den Dialog; die bereits angewendeten Vorschlaege "
            "bleiben bestehen."
        )
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(cancel_btn)
        layout.addLayout(buttons)

        self.setLayout(layout)
        self.setMinimumWidth(420)

    def decisions(self) -> dict:
        return {
            key: combo.currentData()
            for key, combo in self._combos.items()
        }
