"""Screenshots fuer die Hilfe (hilfe/bilder/) headless aus den Beispieldaten.

Aufruf (Projektstamm):  QT_QPA_PLATFORM=offscreen uv run python tools/make_screenshots.py
Nach UI-Aenderungen erneut laufen lassen. Schreibt nichts in data/.
"""
from __future__ import annotations
import copy
import os
import sys
from datetime import date
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu --no-sandbox")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / "hilfe" / "bilder"

from PySide6.QtCore import QTimer, QEventLoop, QUrl, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

import main as m  # noqa: E402
from models import ShiftEntry, ShiftType, set_day_kind  # noqa: E402
from scheduling.engine import generate, Conflict, ConflictOption  # noqa: E402


def pump(ms=150):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def shot(widget, name):
    pump(80)
    pix = widget.grab()
    pix.save(str(OUT / f"{name}.png"), "PNG")
    print(f"  {name}.png  {pix.width()}x{pix.height()}")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    app = m.JohannaApp()
    app.set_color_scheme("ozean", False)
    win = app.window
    win.resize(1480, 900)
    win.show()
    # Start-Dialoge (Ablageordner) zur Not wegklicken
    def closer():
        for w in app.app.topLevelWidgets():
            if isinstance(w, QMessageBox):
                w.accept()
    t = QTimer(); t.setInterval(100); t.timeout.connect(closer); t.start()
    pump(800)

    # Beispielplan: Dezember mit allen Zellzustaenden
    plan = copy.deepcopy(app.plan)
    y, mo = plan.year, plan.month
    a = plan.assistants
    set_day_kind(a[0].constraints, [date(y, mo, d) for d in (3, 4, 5)], "urlaub")
    set_day_kind(a[1].constraints, [date(y, mo, 10), date(y, mo, 11)], "block")
    a[1].constraints.free_wish_quota = 1
    set_day_kind(a[3].constraints, [date(y, mo, d) for d in range(15, 19)], "wish")
    a[3].constraints.work_wish_quota = 2
    plan.schedule[20] = [ShiftEntry(a[4].id, ShiftType.FULL, candidate=True),
                         ShiftEntry(a[5].id, ShiftType.FULL, candidate=True)]
    plan.notes[8] = "Dienst startet erst um 14:00 Uhr"
    generate(plan, 42)
    app.plan = plan
    app.plan_tab.set_plan(plan); app.absence_tab.set_plan(plan); app.team_tab.set_plan(plan)
    win.set_title_plan(y, mo)
    win.status_bar.showMessage("Bereit")
    win.tab_widget.setCurrentIndex(0)
    pump(300)
    print("Screenshots:")
    shot(win, "hauptfenster")
    shot(win.control_bar, "steuerleiste")
    shot(app.plan_tab.stamp_box, "stempel")
    shot(app.plan_tab.import_btn, "import_button")
    shot(app.plan_tab.control_bar_widget, "wuerfeln")
    shot(win.month_selector, "monatswaehler")
    shot(app.plan_tab.table, "raster")
    shot(app.plan_tab.summary_label, "zusammenfassung")
    shot(app.plan_tab.warnings_label, "warnungen")

    win.tab_widget.setCurrentIndex(1); pump(300)
    shot(app.absence_tab, "urlaub_tab")
    app.absence_tab.side_tabs.setCurrentWidget(app.absence_tab.notes_panel); pump(200)
    shot(app.absence_tab.notes_panel, "notizen")

    win.tab_widget.setCurrentIndex(2); pump(300)
    shot(app.team_tab, "team_tab")

    # Dialoge
    from ui.import_dialog import ImportDialog
    from ui.conflict_dialog import ConflictDialog
    from ui.color_settings_dialog import ColorSettingsDialog
    dlg = ImportDialog(plan, win)
    dlg.text_edit.setPlainText(
        f"Hallo Johanna, hier meine Tage.\n"
        f"JA1;{y}-{mo:02d};{a[1].id};T:{y}-{mo:02d}-02T09:12:00;U:3,10-14;W:5,6;D:7-9;N:Am%2012.%20erst%20ab%2010;END\n"
        f"JA1;{y}-{mo:02d};{a[2].id};T:{y}-{mo:02d}-03T18:40:00;U:;W:22;D:1-3;N:;END\n"
        f"JA1;{y}-{mo:02d};unbekannt;T:{y}-{mo:02d}-03T18:40:00;U:1;W:;D:;N:;END"
    )
    dlg._refresh(); dlg.resize(1100, 420); dlg.show(); shot(dlg, "import_dialog"); dlg.close()
    conflicts = [
        Conflict(day=9, kind="dienst", options=[
            ConflictOption(a[1].id, True, f"{a[1].name} (ueberplant Nachrang-Freiwunsch)"),
            ConflictOption(a[0].id, True, f"{a[0].name} (ueberplant Vorrang-Freiwunsch)"),
            ConflictOption(None, False, "Tag offen lassen")], proposal=0),
        Conflict(day=23, kind="rb", options=[
            ConflictOption(a[2].id, True, f"{a[2].name} (ueberplant Nachrang-Freiwunsch)"),
            ConflictOption(None, False, "Tag offen lassen")], proposal=0),
    ]
    cd = ConflictDialog(conflicts, win); cd.show(); shot(cd, "konflikt_dialog"); cd.close()
    fd = ColorSettingsDialog(app.settings, win); fd.show(); shot(fd, "farben_dialog"); fd.close()

    # Rueckmeldeformular im Browser-Widget (falls WebEngine vorhanden)
    try:
        from PySide6.QtWebEngineWidgets import QWebEngineView
        from export.form_exporter import render_form
        html = render_form(plan, "planung@beispiel.de")
        tmp = OUT.parent / "_formular_tmp.html"
        tmp.write_text(html, encoding="utf-8")
        view = QWebEngineView(); view.resize(440, 980); view.show()
        loop = QEventLoop(); view.loadFinished.connect(lambda _ok: loop.quit())
        view.load(QUrl.fromLocalFile(str(tmp))); QTimer.singleShot(8000, loop.quit); loop.exec(); pump(1200)
        shot(view, "formular")
        tmp.unlink()
    except Exception as e:  # noqa: BLE001
        print("  (kein Formular-Screenshot:", e, ")")

    win.on_close_request = None
    app.app.quit()


if __name__ == "__main__":
    main()
