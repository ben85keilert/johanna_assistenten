"""Rueckmeldungen importieren (Datei > Rueckmeldungen importieren...,
Import-Button im Dienstplan).

Oben ein Textfeld: Mailtext aus GMX hineinkopieren (oder "Zwischenablage
einfuegen"), beliebig viele Mails hintereinander. Dazu "Dateien waehlen..."
(txt/eml/html) und "Ablageordner durchsuchen" (neue Dateien aus
Formularantworten/). Die Tabelle zeigt jede gefundene Rueckmeldung mit
Helfer, Monat, Zahl der Tage je Art, Bemerkung, was dabei ersetzt wuerde und
ob sie gueltig ist. Erst "Uebernehmen" traegt die gueltigen ein - das macht
der Aufrufer (JohannaApp.apply_feedback_list) mit feedbacks().
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog, QAbstractItemView,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication

from models import MonthPlan, month_label
from feedback import (
    Feedback, parse_text, read_file_text, scan_new_files, existing_counts,
    inbox_root, last_import, is_older_than_last, format_stamp,
)
from feedback.parser import KIND_LABELS
from . import theme

COLUMNS = ["Helfer", "Monat", "Stand", "Urlaub", "Wunsch frei", "Dienstwunsch",
           "Bemerkung", "Ersetzt", "Letzter Import", "Status", "Quelle"]


class ImportDialog(QDialog):
    def __init__(self, plan: MonthPlan, parent=None, initial_files: list[Path] | None = None):
        super().__init__(parent)
        self.plan = plan
        self._by_id = {a.id: a for a in plan.assistants}
        self._file_feedbacks: list[Feedback] = []
        self._feedbacks: list[Feedback] = []
        self.setWindowTitle("Rueckmeldungen importieren")
        self.setMinimumSize(760, 520)

        layout = QVBoxLayout()
        hint = QLabel(
            "Mailtext der Helfer unten einfuegen (mehrere Mails hintereinander "
            "sind in Ordnung - gelesen wird nur die Zeile, die mit JA1 beginnt), "
            "oder Dateien bzw. den Ablageordner einlesen. Eine Rueckmeldung "
            "ersetzt Urlaub, Wunsch und Dienstwunsch des Helfers fuer den "
            "gemeldeten Monat."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.text_edit = QPlainTextEdit()
        self.text_edit.setPlaceholderText("Hier den Mailtext einfuegen ...")
        self.text_edit.setMaximumHeight(140)
        layout.addWidget(self.text_edit)

        buttons = QHBoxLayout()
        paste_btn = QPushButton("Zwischenablage einfuegen")
        paste_btn.clicked.connect(self.paste_clipboard)
        buttons.addWidget(paste_btn)
        files_btn = QPushButton("Dateien waehlen...")
        files_btn.setToolTip("Antworten als .txt, .eml oder .html")
        files_btn.clicked.connect(self.choose_files)
        buttons.addWidget(files_btn)
        inbox_btn = QPushButton("Ablageordner durchsuchen")
        inbox_btn.setToolTip(
            f"Neue Dateien in {inbox_root()} (alle Monatsordner) einlesen"
        )
        inbox_btn.clicked.connect(self.scan_inbox)
        buttons.addWidget(inbox_btn)
        buttons.addStretch()
        layout.addLayout(buttons)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(theme.ROW_HEIGHT)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(COLUMNS.index("Bemerkung"), QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(COLUMNS.index("Status"), QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, stretch=1)

        self.summary_label = QLabel()
        self.summary_label.setProperty("role", "muted")
        layout.addWidget(self.summary_label)

        bottom = QHBoxLayout()
        bottom.addStretch()
        self.ok_btn = QPushButton("Uebernehmen")
        self.ok_btn.setProperty("role", "primary")
        self.ok_btn.setDefault(True)
        self.ok_btn.clicked.connect(self.accept)
        bottom.addWidget(self.ok_btn)
        cancel_btn = QPushButton("Abbrechen")
        cancel_btn.clicked.connect(self.reject)
        bottom.addWidget(cancel_btn)
        layout.addLayout(bottom)
        self.setLayout(layout)

        # Tippen/Einfuegen im Textfeld: kurz warten, dann neu lesen
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(300)
        self._timer.timeout.connect(self._refresh)
        self.text_edit.textChanged.connect(self._timer.start)

        if initial_files:
            self._add_files(initial_files)
        else:
            # Zwischenablage mit Rueckmeldung? Dann gleich uebernehmen
            clip = QGuiApplication.clipboard().text()
            if "JA1;" in clip:
                self.text_edit.setPlainText(clip)
        self._refresh()

    # --- Quellen ----------------------------------------------------------

    def paste_clipboard(self):
        clip = QGuiApplication.clipboard().text()
        if clip.strip():
            self.text_edit.appendPlainText(clip)

    def choose_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Antwortdateien waehlen", str(inbox_root()),
            "Antworten (*.txt *.eml *.html *.htm);;Alle Dateien (*)",
        )
        if paths:
            self._add_files([Path(p) for p in paths])

    def scan_inbox(self):
        files = scan_new_files()
        if not files:
            self.summary_label.setText(
                f"Keine neuen Dateien im Ablageordner {inbox_root()}."
            )
            return
        self._add_files(files)

    def _add_files(self, paths: list[Path]):
        known = {fb.path for fb in self._file_feedbacks}
        for path in paths:
            if path in known:
                continue
            try:
                text = read_file_text(path)
            except Exception as e:
                self._file_feedbacks.append(
                    Feedback(source=path.name, path=path, error=f"Datei nicht lesbar: {e}")
                )
                continue
            found = parse_text(text, source=path.name)
            if not found:
                found = [Feedback(source=path.name, path=path,
                                  error="keine Rueckmeldung (JA1-Zeile) in der Datei")]
            for fb in found:
                fb.path = path
            self._file_feedbacks.extend(found)
        self._refresh()

    # --- Tabelle ------------------------------------------------------------

    def _refresh(self):
        pasted = parse_text(self.text_edit.toPlainText(), source="Text")
        self._feedbacks = self._file_feedbacks + pasted
        for fb in self._feedbacks:
            if fb.ok and fb.assistant_id not in self._by_id:
                fb.error = "Helfer-ID unbekannt (Formular aus altem Team?)"
        self.table.setRowCount(len(self._feedbacks))
        colors = theme.colors()
        for row, fb in enumerate(self._feedbacks):
            assistant = self._by_id.get(fb.assistant_id)
            name = assistant.name if assistant else (fb.assistant_id or "?")
            month = month_label(fb.year, fb.month) if fb.month else ""
            replaced = last_text = ""
            status = "OK" if fb.ok else f"Fehler: {fb.error}"
            older = False
            if fb.ok and assistant is not None:
                old = existing_counts(assistant, fb.year, fb.month)
                replaced = ", ".join(
                    f"{n} {KIND_LABELS[k]}" for k, n in old.items() if n
                ) or "nichts"
                last = last_import(assistant, fb.year, fb.month)
                if last:
                    last_text = (
                        f"Stand {format_stamp(last.get('stand', '')) or 'unbekannt'}, "
                        f"eingelesen {format_stamp(last.get('eingelesen', ''))}"
                    )
                older = is_older_than_last(assistant, fb)
                if older:
                    status = "OK, aber aelter als der letzte Import (Rueckfrage)"
            values = [
                name, month, format_stamp(fb.stamp) or ("ohne Zeitstempel" if fb.ok else ""),
                str(fb.count("urlaub")) if fb.ok else "",
                str(fb.count("block")) if fb.ok else "",
                str(fb.count("wish")) if fb.ok else "",
                fb.note, replaced, last_text, status, fb.source,
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if not fb.ok or (older and col == COLUMNS.index("Status")):
                    item.setForeground(colors_qcolor(colors.warning))
                if col in (3, 4, 5):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, col, item)
        valid = [fb for fb in self._feedbacks if fb.ok]
        invalid = len(self._feedbacks) - len(valid)
        self.ok_btn.setEnabled(bool(valid))
        if not self._feedbacks:
            self.summary_label.setText("Noch keine Rueckmeldung gefunden.")
        else:
            text = f"{len(valid)} gueltige Rueckmeldung(en)"
            if invalid:
                text += f", {invalid} fehlerhaft (werden nicht uebernommen)"
            self.summary_label.setText(text + ".")

    def feedbacks(self) -> list[Feedback]:
        """Die gueltigen Rueckmeldungen nach OK."""
        return [fb for fb in self._feedbacks if fb.ok]


def colors_qcolor(hex_color: str):
    from PySide6.QtGui import QColor
    return QColor(hex_color)
