"""Reiter "Notizen" im Tab "Urlaub und Notizen": alle Tagesnotizen des
Monats auf einen Blick - vor allem fuer die anderen im Team gedacht.

Oben die Tage des Monats mit ihrer Notiz (optional nur Tage mit Notiz) -
ein einfacher Klick in die Notiz-Spalte bearbeitet sie direkt in der
Tabelle (Enter uebernimmt, Esc verwirft). Mehrzeilige Notizen stehen dort
einzeilig mit LINE_MARK zwischen den Zeilen; bequemer bearbeitet man sie im
Editor darunter. Beide Wege gelten sofort (leerer Text = keine Notiz).
"Alle kopieren" und "Exportieren..." geben die Notizen gesammelt aus
(export/notes_exporter.py). Angezeigt wird der Monat des Dienstplans.
"""
from datetime import date
import calendar

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QPlainTextEdit,
    QStyledItemDelegate, QLineEdit,
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QColor, QFont, QGuiApplication

from models import MonthPlan, WEEKDAYS_DE, holiday_name, month_label
from export.notes_exporter import day_staff, notes_text
from . import theme

# Notiz-Aenderungen erst nach kurzer Tipp-Pause melden (Plan neu zeichnen);
# im Plan selbst steht der Text sofort
NOTIFY_DELAY_MS = 250

# Zeilenumbruch einer mehrzeiligen Notiz in der einzeiligen Tabellenansicht
# (und beim Bearbeiten direkt in der Tabelle - bleibt so erhalten)
LINE_MARK = " \u23CE "

COL_DAY, COL_NOTE = 0, 1


def to_single_line(text: str) -> str:
    return LINE_MARK.join(text.splitlines())


def from_single_line(text: str) -> str:
    lines = text.replace(LINE_MARK.strip(), "\n").splitlines()
    return "\n".join(line.strip() for line in lines).strip()


class _InlineNoteDelegate(QStyledItemDelegate):
    """Einzeiliger Editor direkt in der Notiz-Spalte; schreibt ueber
    NotesPanel.set_note in den Plan (nicht in das Tabellen-Item)."""

    def __init__(self, panel: "NotesPanel"):
        super().__init__(panel)
        self.panel = panel

    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        editor.setPlaceholderText("Notiz eingeben ... (Enter uebernimmt)")
        return editor

    def setEditorData(self, editor, index):
        day = self.panel.day_of_row(index.row())
        editor.setText(to_single_line(self.panel.note(day)) if day else "")

    def setModelData(self, editor, model, index):
        day = self.panel.day_of_row(index.row())
        if day:
            self.panel.set_note(day, from_single_line(editor.text()))


class NotesPanel(QWidget):
    # Notiz geaendert -> Dienstplan neu zeichnen, als geaendert markieren
    notes_changed = Signal()
    # "Exportieren..." -> JohannaApp.export_notes (Zielordner-Dialog)
    export_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.plan: MonthPlan | None = None
        self._day: int | None = None
        self._loading = False
        self._notify_timer = QTimer(self)
        self._notify_timer.setSingleShot(True)
        self._notify_timer.setInterval(NOTIFY_DELAY_MS)
        self._notify_timer.timeout.connect(self.notes_changed.emit)
        self._feedback_timer = QTimer(self)
        self._feedback_timer.setSingleShot(True)
        self._feedback_timer.setInterval(3000)
        self._feedback_timer.timeout.connect(lambda: self.feedback_label.setText(""))
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        head = QHBoxLayout()
        self.title_label = QLabel()
        bold = QFont()
        bold.setBold(True)
        self.title_label.setFont(bold)
        head.addWidget(self.title_label)
        head.addStretch()
        self.only_notes_btn = QPushButton("Nur Tage mit Notiz")
        self.only_notes_btn.setCheckable(True)
        self.only_notes_btn.setToolTip("Tage ohne Notiz ausblenden.")
        self.only_notes_btn.toggled.connect(self.refresh)
        head.addWidget(self.only_notes_btn)
        layout.addLayout(head)

        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Tag", "Notiz"])
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(theme.ROW_HEIGHT)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        # Ein einfacher Klick in die Notiz-Spalte startet die Bearbeitung
        # (CurrentChanged); Tippen auf einer gewaehlten Zeile ebenso
        edit = QAbstractItemView.EditTrigger
        self.table.setEditTriggers(
            edit.CurrentChanged | edit.SelectedClicked | edit.DoubleClicked
            | edit.EditKeyPressed | edit.AnyKeyPressed
        )
        self.table.setItemDelegateForColumn(COL_NOTE, _InlineNoteDelegate(self))
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(COL_DAY, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(COL_NOTE, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self.table, stretch=3)

        self.editor_label = QLabel()
        layout.addWidget(self.editor_label)
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText(
            "Notiz zu diesem Tag, z. B. \"Dienst startet um 14:00 Uhr\" "
            "(leer = keine Notiz)"
        )
        self.editor.setMinimumHeight(70)
        self.editor.textChanged.connect(self._on_text_changed)
        layout.addWidget(self.editor, stretch=1)

        buttons = QHBoxLayout()
        self.clear_btn = QPushButton("Notiz loeschen")
        self.clear_btn.setToolTip("Notiz des gewaehlten Tages entfernen.")
        self.clear_btn.clicked.connect(self.editor.clear)
        buttons.addWidget(self.clear_btn)
        self.feedback_label = QLabel()
        self.feedback_label.setProperty("role", "muted")
        buttons.addWidget(self.feedback_label)
        buttons.addStretch()
        copy_btn = QPushButton("Alle kopieren")
        copy_btn.setToolTip(
            "Alle Notizen des Monats samt Eingeteilten in die Zwischenablage "
            "- zum Weitergeben per Mail oder Messenger."
        )
        copy_btn.clicked.connect(self.copy_all)
        buttons.addWidget(copy_btn)
        export_btn = QPushButton("Exportieren...")
        export_btn.setToolTip("Alle Notizen des Monats als Textdatei speichern.")
        export_btn.clicked.connect(self.export_requested.emit)
        buttons.addWidget(export_btn)
        layout.addLayout(buttons)

        self.setLayout(layout)
        self._update_editor_state()

    # --- Aussenschnittstelle -------------------------------------------

    def set_plan(self, plan: MonthPlan):
        self.plan = plan
        self._day = None
        self.refresh()

    def note(self, day: int) -> str:
        return (self.plan.notes.get(day) or "").strip() if self.plan else ""

    def day_of_row(self, row: int) -> int | None:
        item = self.table.item(row, COL_DAY)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def set_note(self, day: int, text: str):
        """Notiz eines Tages setzen (leer = entfernen) - aus der Tabelle oder
        dem Editor; Liste, Editor und Plan bleiben synchron."""
        if not self.plan or text == self.note(day):
            return
        if text:
            self.plan.notes[day] = text
        else:
            self.plan.notes.pop(day, None)
        row = self._row_of(day)
        if row is not None:
            self._loading = True
            self._fill_row(row, day)
            self._loading = False
        if day == self._day and not self.editor.hasFocus():
            self._load_editor()
        self._notify_timer.start()

    def select_day(self, day: int, focus: bool = False):
        """Tag in der Liste waehlen (z. B. nach Klick im Kalender)."""
        row = self._row_of(day)
        if row is None and self.only_notes_btn.isChecked():
            # Tag ohne Notiz ist ausgeblendet - Filter loesen
            self.only_notes_btn.setChecked(False)
            row = self._row_of(day)
        if row is not None:
            self.table.setCurrentCell(row, COL_DAY)
            self.table.scrollToItem(self.table.item(row, COL_DAY))
        if focus:
            self.editor.setFocus()

    def refresh(self):
        """Liste neu aufbauen; Auswahl und Editor bleiben beim Tag."""
        if not self.plan:
            return
        days_in_month = calendar.monthrange(self.plan.year, self.plan.month)[1]
        only_notes = self.only_notes_btn.isChecked()
        days = [
            d for d in range(1, days_in_month + 1)
            if not only_notes or self.note(d) or d == self._day
        ]

        self._loading = True
        self.table.setRowCount(len(days))
        for row, day in enumerate(days):
            self._fill_row(row, day)
        self._loading = False

        self.title_label.setText(
            f"Notizen {month_label(self.plan.year, self.plan.month)}"
        )
        row = self._row_of(self._day) if self._day else None
        if row is not None:
            self.table.setCurrentCell(row, COL_DAY)
        else:
            self._day = None
            self.table.clearSelection()
        self._load_editor()

    # --- Liste ---------------------------------------------------------

    def _row_of(self, day: int | None) -> int | None:
        for row in range(self.table.rowCount()):
            if self.day_of_row(row) == day:
                return row
        return None

    def _item(self, row: int, col: int) -> QTableWidgetItem:
        """Vorhandenes Item weiterverwenden - beim Uebernehmen aus der
        Tabelle liegt der Editor noch darauf und soll es nicht verlieren."""
        item = self.table.item(row, col)
        if item is None:
            item = QTableWidgetItem()
            self.table.setItem(row, col, item)
        return item

    def _fill_row(self, row: int, day: int):
        d = date(self.plan.year, self.plan.month, day)
        note = self.note(day)
        holiday = holiday_name(self.plan.year, self.plan.month, day)
        day_item = self._item(row, COL_DAY)
        day_item.setText(
            f"{WEEKDAYS_DE[d.weekday()]} {d:%d.%m.}"
            + (f"  {theme.NOTE_ICON}" if note else "")
        )
        day_item.setData(Qt.ItemDataRole.UserRole, day)
        # Nur die Notiz-Spalte ist (per Klick) bearbeitbar
        day_item.setFlags(day_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        # Mehrzeilige Notizen in der Liste einzeilig, voller Text im Tooltip
        note_item = self._item(row, COL_NOTE)
        note_item.setText(to_single_line(note))
        tooltip = "\n\n".join(filter(None, [holiday, note, day_staff(self.plan, day)]))
        gray = d.weekday() >= 5 or holiday is not None
        for item in (day_item, note_item):
            font = item.font()
            font.setBold(bool(note))
            item.setFont(font)
            item.setData(
                Qt.ItemDataRole.BackgroundRole,
                QColor(theme.colors().weekend) if gray else None,
            )
            item.setToolTip(tooltip)

    def _on_selection_changed(self):
        if self._loading:
            return
        rows = self.table.selectionModel().selectedRows()
        self._day = self.day_of_row(rows[0].row()) if rows else None
        self._load_editor()

    # --- Editor --------------------------------------------------------

    def _load_editor(self):
        """Editor auf den gewaehlten Tag setzen (ohne Aenderung zu melden)."""
        if self._day is not None and self.editor.toPlainText().strip() == self.note(self._day):
            # Gleicher Text (z. B. Liste nach eigener Eingabe neu gebaut):
            # Cursor und Leerzeichen beim Tippen nicht stoeren
            self._update_editor_state()
            return
        self._loading = True
        self.editor.setPlainText(self.note(self._day) if self._day else "")
        self._loading = False
        self._update_editor_state()

    def _update_editor_state(self):
        has_day = self.plan is not None and self._day is not None
        self.editor.setEnabled(has_day)
        self.clear_btn.setEnabled(has_day)
        if has_day:
            d = date(self.plan.year, self.plan.month, self._day)
            self.editor_label.setText(
                f"Notiz fuer {WEEKDAYS_DE[d.weekday()]} {d:%d.%m.%Y} "
                "(mehrzeilig):"
            )
        else:
            self.editor_label.setText("Tag in der Liste waehlen, um die Notiz zu bearbeiten.")

    def _on_text_changed(self):
        if self._loading or not self.plan or self._day is None:
            return
        self.set_note(self._day, self.editor.toPlainText().strip())

    # --- Gesammelt ausgeben ---------------------------------------------

    def copy_all(self):
        if not self.plan:
            return
        QGuiApplication.clipboard().setText(notes_text(self.plan))
        self.feedback_label.setText("In die Zwischenablage kopiert.")
        self._feedback_timer.start()
