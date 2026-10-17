"""PDF-Export im Hochformat: Seite 1 = ganzer Monat, Seite 2 = Notizen,
Zusammenfassung und Legende.

Der Ausdruck ist fuer das ganze Team gedacht und zeigt deshalb nur Dienste
und Rufbereitschaften - keine Urlaube, keine Freiwuensche (die anderen
sollen nicht sehen, wer wann frei haben will). Farben je Eintragsart wie im
Planraster (AppSettings.entry_colors), aber alle Eintraege einheitlich
kraeftig - ob ein Eintrag schon fixiert oder noch gewuerfelt ist, spielt fuer
den Aushang keine Rolle. Wochenenden und bayerische Feiertage grau. Nicht
gewaehlte Kandidaten erscheinen nicht - der Ausdruck zeigt nur wirksame
Zuteilungen.

Tagesnotizen sind deutlich markiert: der Tageskopf ist farbig hinterlegt
und traegt "Notiz", die ganze Tagesspalte ist umrahmt, und jede Zelle der
an dem Tag Eingeteilten traegt nochmals "Notiz". Der Text steht auf Seite 2.

Seitenaufteilung mit explizitem PageBreak, damit keine Tabelle mitten
umbricht: Seite 1 = beide Monatshaelften untereinander, Seite 2 = Notizen,
Zusammenfassung, Legende und Feiertage.
"""
from pathlib import Path
import math
import calendar
from datetime import date as dt_date
from xml.sax.saxutils import escape

from reportlab.lib import pagesizes
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak,
)
from reportlab.lib import colors

from models import (
    MonthPlan, ShiftType, SHIFT_LABELS, SHIFT_NAMES, MONTHS_DE, WEEKDAYS_DE,
    is_duty, is_effective, bavarian_holidays, holiday_name,
)
from persistence import AppSettings
from .notes_exporter import day_label, day_staff, month_notes

PAGE_SIZE = pagesizes.A4  # Hochformat
MARGIN = 1.0 * cm
NAME_COL_WIDTH = 2.6 * cm
HEADER_ROW_H = 1.05 * cm
# Zeilenhoehe der Helfer: so gross wie moeglich, damit beide Haelften die
# Seite fuellen - aber nie hoeher als MAX (kleine Teams) bzw. kleiner als MIN
BODY_ROW_H_MAX = 1.1 * cm
BODY_ROW_H_MIN = 0.5 * cm
# Titel + Abstand zwischen den Haelften + Reserve (Hoehe auf Seite 1)
PAGE1_OVERHEAD = 3.0 * cm

CELL_PT = 8
HEADER_PT = 7.5

# Wochenend-/Feiertagsgrau: neutral und hell - der Ausdruck ist unabhaengig
# vom gewaehlten Farbschema (ui/theme.py) immer fuer Papier gemacht
GRAY_DAY = (235 / 255.0, 235 / 255.0, 235 / 255.0)

# Notiz-Markierung: Tageskopf hinterlegt, Spalte umrahmt, Hinweis in Zellen
NOTE_FILL = "#FFE7A3"
NOTE_EDGE = "#C77C00"
# Schrift des gelben Notiz-Schildchens in den Dienstzellen: dunkel, damit
# es auf jeder Dienstfarbe lesbar bleibt
NOTE_TEXT = "#6B4000"
NOTE_MARK = "Notiz"


def _hex_rgb(hex_color: str) -> tuple[float, float, float]:
    hex_color = hex_color.lstrip("#")
    return (
        int(hex_color[0:2], 16) / 255.0,
        int(hex_color[2:4], 16) / 255.0,
        int(hex_color[4:6], 16) / 255.0,
    )


def _entry_color(settings: AppSettings, key: str) -> colors.Color:
    return colors.Color(*_hex_rgb(settings.entry_colors.get(key, "#9E9E9E")))


def _is_gray_day(year: int, month: int, day: int) -> bool:
    return (dt_date(year, month, day).weekday() >= 5
            or holiday_name(year, month, day) is not None)


def _has_note(plan: MonthPlan, day: int) -> bool:
    return bool((plan.notes.get(day) or "").strip())


def _cell_content(plan: MonthPlan, settings: AppSettings, assistant, day: int,
                  style: ParagraphStyle):
    """Inhalt und Hintergrundfarbe einer Planzelle.

    Nur Dienste und Rufbereitschaften (keine Urlaube/Wuensche), ohne
    Kandidaten-Vorschlaege; Farbe der Eintragsart, immer kraeftig."""
    entries = [e for e in plan.schedule.get(day, [])
               if e.assistant_id == assistant.id and is_effective(e)]
    duty = next((e for e in entries if is_duty(e.shift_type)), None)
    oncall = next((e for e in entries
                   if e.shift_type == ShiftType.ON_CALL), None)

    entry = duty or oncall
    if entry is None:
        return "", None

    label = SHIFT_LABELS.get(entry.shift_type, "")
    size = CELL_PT
    if duty is not None and oncall is not None:
        # Doppelbelegung (warnt der Validator) - beides zeigen, kleiner
        label += "/RB"
        size = CELL_PT - 2.5
    text = f'<b><font size="{size}">{escape(label)}</font></b>'
    if _has_note(plan, day):
        # Notiz nochmals in der Zelle jedes an dem Tag Eingeteilten - als
        # gelbes Schildchen wie der Tageskopf
        text += (f'<br/><font size="{CELL_PT - 2}" color="{NOTE_TEXT}" '
                 f'backColor="{NOTE_FILL}"><b>&nbsp;{NOTE_MARK}&nbsp;</b></font>')
    return Paragraph(text, style), _entry_color(settings, entry.shift_type.value)


def _plan_table(plan: MonthPlan, settings: AppSettings, first_day: int,
                last_day: int, day_width: float, body_row_h: float,
                styles: dict) -> Table:
    """Eine Plantabelle fuer einen Tagesbereich (Zeile = Helfer)."""
    year, month = plan.year, plan.month
    days = list(range(first_day, last_day + 1))

    header = [Paragraph("<b>Helfer</b>", styles["name"])]
    for day in days:
        weekday = WEEKDAYS_DE[dt_date(year, month, day).weekday()]
        text = f"<b>{day}</b><br/>{weekday}"
        if _has_note(plan, day):
            text += f'<br/><font color="{NOTE_EDGE}"><b>{NOTE_MARK}</b></font>'
        header.append(Paragraph(text, styles["header"]))
    data = [header]
    style_list = [
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
    ]

    # Wochenenden und Feiertage grau hinterlegen (ganze Spalte inkl. Kopf)
    gray = colors.Color(*GRAY_DAY)
    for col, day in enumerate(days, 1):
        if _is_gray_day(year, month, day):
            style_list.append(("BACKGROUND", (col, 0), (col, -1), gray))

    for row, assistant in enumerate(plan.assistants, 1):
        cells = [Paragraph(escape(assistant.name), styles["name"])]
        for col, day in enumerate(days, 1):
            content, color = _cell_content(
                plan, settings, assistant, day, styles["cell"]
            )
            cells.append(content)
            if color is not None:
                style_list.append(("BACKGROUND", (col, row), (col, row), color))
        data.append(cells)

    # Notiz-Tage: Kopf farbig hinterlegt, ganze Spalte kraeftig umrahmt
    # (nach GRID und Hintergruenden, damit Rahmen und Farbe oben liegen)
    for col, day in enumerate(days, 1):
        if _has_note(plan, day):
            style_list.append(
                ("BACKGROUND", (col, 0), (col, 0), colors.HexColor(NOTE_FILL))
            )
            style_list.append(
                ("BOX", (col, 0), (col, -1), 1.6, colors.HexColor(NOTE_EDGE))
            )

    table = Table(
        data,
        colWidths=[NAME_COL_WIDTH] + [day_width] * len(days),
        rowHeights=[HEADER_ROW_H] + [body_row_h] * len(plan.assistants),
    )
    table.hAlign = "LEFT"
    table.setStyle(TableStyle(style_list))
    return table


def _legend_table(settings: AppSettings) -> Table:
    """Farb-Legende: nur was im Ausdruck vorkommt (keine Urlaube/Wuensche)."""
    items = [
        (_entry_color(settings, t.value), SHIFT_NAMES[t]) for t in ShiftType
    ]
    items += [
        (colors.Color(*GRAY_DAY), "Wochenende oder Feiertag (Bayern)"),
        (colors.HexColor(NOTE_FILL),
         f"\"{NOTE_MARK}\" im Tageskopf und in den Diensten = Tagesnotiz "
         "(Text oben unter Notizen)"),
    ]
    data = [["", label] for _color, label in items]
    style_list = [
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (0, -1), 0.5, colors.grey),
    ]
    for row, (color, _label) in enumerate(items):
        style_list.append(("BACKGROUND", (0, row), (0, row), color))
    # Notiz-Feld wie im Plan umrahmt
    note_row = len(items) - 1
    style_list.append(
        ("BOX", (0, note_row), (0, note_row), 1.6, colors.HexColor(NOTE_EDGE))
    )
    table = Table(data, colWidths=[0.8 * cm, 15.0 * cm])
    table.hAlign = "LEFT"
    table.setStyle(TableStyle(style_list))
    return table


def _summary_table(plan: MonthPlan) -> Table:
    summary_data = [["Helfer", "Dienste gesamt"]
                    + [SHIFT_LABELS[t] for t in ShiftType]]
    for assistant in plan.assistants:
        counts = {t: 0 for t in ShiftType}
        for entries in plan.schedule.values():
            for e in entries:
                if e.assistant_id == assistant.id and is_effective(e):
                    counts[e.shift_type] += 1
        # Gewichtete Dienstzahl (VOLL=1, Tag/Nacht=0,5); RB zaehlt separat
        total = counts[ShiftType.FULL] + 0.5 * (
            counts[ShiftType.HALF_MORNING] + counts[ShiftType.HALF_AFTERNOON]
        )
        summary_data.append(
            [assistant.name, f"{total:g}"] + [str(counts[t]) for t in ShiftType]
        )

    table = Table(summary_data, colWidths=[4.0 * cm, 2.8 * cm] + [2.4 * cm] * 4)
    table.hAlign = "LEFT"
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.Color(0.94, 0.94, 0.94)]),
    ]))
    return table


def export_pdf(plan: MonthPlan, folder: str | Path,
               settings: AppSettings | None = None) -> str:
    if settings is None:
        settings = AppSettings()
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)

    year, month = plan.year, plan.month
    days_in_month = calendar.monthrange(year, month)[1]
    pdf_file = folder / f"plan_{year}_{month:02d}.pdf"

    doc = SimpleDocTemplate(
        str(pdf_file),
        pagesize=PAGE_SIZE,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        title=f"Dienstplan {MONTHS_DE[month]} {year}",
    )

    sample = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "CustomTitle", parent=sample["Heading1"], fontSize=16,
        textColor=colors.black, spaceAfter=8,
    )
    body_style = ParagraphStyle(
        "CustomBody", parent=sample["Normal"], fontSize=9, leading=12,
    )
    note_style = ParagraphStyle(
        "Note", parent=body_style, spaceAfter=5, leftIndent=8,
    )
    styles = {
        "cell": ParagraphStyle(
            "Cell", parent=sample["Normal"], fontSize=CELL_PT,
            leading=CELL_PT + 1.5, alignment=TA_CENTER,
        ),
        "header": ParagraphStyle(
            "Header", parent=sample["Normal"], fontSize=HEADER_PT,
            leading=HEADER_PT + 1.5, alignment=TA_CENTER,
        ),
        "name": ParagraphStyle(
            "Name", parent=sample["Normal"], fontSize=CELL_PT, leading=CELL_PT + 1.5,
        ),
    }

    # Beide Monatshaelften untereinander auf Seite 1; die Zeilenhoehe passt
    # sich der Teamgroesse an, damit nichts auf Seite 2 rutscht
    half = math.ceil(days_in_month / 2)
    available_width = PAGE_SIZE[0] - 2 * MARGIN
    day_width = (available_width - NAME_COL_WIDTH) / half
    available_height = PAGE_SIZE[1] - 2 * MARGIN - PAGE1_OVERHEAD - 2 * HEADER_ROW_H
    rows = max(1, 2 * len(plan.assistants))
    body_row_h = max(BODY_ROW_H_MIN, min(BODY_ROW_H_MAX, available_height / rows))

    story = [
        Paragraph(f"Dienstplan {MONTHS_DE[month]} {year}", title_style),
        _plan_table(plan, settings, 1, half, day_width, body_row_h, styles),
        Spacer(1, 0.6 * cm),
        _plan_table(plan, settings, half + 1, days_in_month, day_width,
                    body_row_h, styles),
        PageBreak(),
    ]

    # Seite 2: Notizen, Zusammenfassung, Legende, Feiertage
    story.append(Paragraph(
        f"Dienstplan {MONTHS_DE[month]} {year} - Notizen und Uebersicht",
        title_style,
    ))
    story.append(Paragraph("Notizen", sample["Heading2"]))
    notes = month_notes(plan)
    if not notes:
        story.append(Paragraph("Keine Notizen in diesem Monat.", body_style))
    for day, text in notes:
        staff = day_staff(plan, day)
        staff_html = f' <font color="#666666">({escape(staff)})</font>' if staff else ""
        story.append(Paragraph(
            f'<font color="{NOTE_EDGE}"><b>{NOTE_MARK}</b></font> '
            f"<b>{escape(day_label(plan, day))}</b>{staff_html}<br/>"
            + escape(text).replace("\n", "<br/>"),
            note_style,
        ))

    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph("Zusammenfassung", sample["Heading2"]))
    story.append(_summary_table(plan))

    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph("Legende", sample["Heading2"]))
    story.append(_legend_table(settings))

    month_holidays = sorted(
        (d, name) for d, name in bavarian_holidays(year).items()
        if d.month == month
    )
    if month_holidays:
        story.append(Spacer(1, 0.3 * cm))
        story.append(Paragraph("Feiertage", sample["Heading2"]))
        for d, name in month_holidays:
            story.append(Paragraph(f"{d.day:02d}.{month:02d}.: {name}", body_style))

    doc.build(story)
    return str(pdf_file)
