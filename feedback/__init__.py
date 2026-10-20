"""Rueckmeldungen der Helfer (Formular -> Mailtext -> Programm).

parser.py  liest die Maschinenzeile des Rueckmeldeformulars aus beliebigem
           Text oder aus Dateien (txt/html/eml) und prueft sie
inbox.py   der Ablageordner "Formularantworten" neben dem Programmordner:
           ein Unterordner je Monat, dort legt die Planerin die Antworten
           ab; neue Dateien werden beim Start / "Aktualisieren" eingelesen
apply.py   traegt eine Rueckmeldung in die Abwesenheiten/Wuensche eines
           Helfers ein (ersetzt dessen Eintraege dieses Monats)
"""
from .parser import Feedback, FORMAT_ID, extract_blocks, parse_block, parse_text, read_file_text, format_stamp
from .inbox import (
    inbox_root, month_folder, ensure_month_folders, scan_new_files,
    mark_processed, append_protocol, INBOX_MONTHS_AHEAD,
)
from .apply import existing_counts, apply_feedback, last_import, is_older_than_last

__all__ = [
    "Feedback", "FORMAT_ID", "extract_blocks", "parse_block", "parse_text",
    "read_file_text", "format_stamp", "inbox_root", "month_folder", "ensure_month_folders",
    "scan_new_files", "mark_processed", "append_protocol", "INBOX_MONTHS_AHEAD",
    "existing_counts", "apply_feedback", "last_import", "is_older_than_last",
]
