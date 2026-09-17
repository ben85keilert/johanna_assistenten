"""PDF-Export: gleiche Farblogik wie das Planraster, feste Seitenaufteilung.

Farben kommen aus AppSettings.entry_colors (je Eintragsart, wie im
CellDelegate): feste Eintraege deckend, noch in Planung befindliche blass;
Urlaub "U" und Block "X" in ihren Farben; Wochenenden und bayerische
Feiertage grau. Nicht gewaehlte Kandidaten erscheinen nicht - der Ausdruck
zeigt nur wirksame Zuteilungen.

Seitenaufteilung mit expliziten PageBreaks, damit keine Tabelle mitten
umbricht: Seite 1 = erste Monatshaelfte, Seite 2 = zweite Haelfte,
Seite 3 = Zusammenfassung + Legende + Notizen + Feiertage.
"""
from pathlib import Path
import math
import calendar
from datetime import date as dt_date
from xml.sax.saxutils import escape

from reportlab.lib import pagesizes
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak,
)
from reportlab.lib import colors

from models import MonthPlan, ShiftType, is_duty, is_effective, bavarian_holidays, holiday_name
from persistence import AppSettings
from scheduling.engine import is_on_vacation, is_blocked

SHIFT_LABELS = {
    ShiftType.FULL: "VOLL",
    ShiftType.HALF_MORNING: "VM",
    ShiftType.HALF_AFTERNOON: "NM",
    ShiftType.ON_CALL: "RB",
}

PAGE_SIZE = pagesizes.landscape(pagesizes.A4)
MARGIN = 0.5 * cm
NAME_COL_WIDTH = 2.5 * cm

WEEKDAYS_DE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
MONTHS_DE = ["", "Januar", "Februar", "Maerz", "April", "Mai", "Juni",
             "Juli", "August", "September", "Oktober", "November", "Dezember"]

# Wochenend-/Feiertagsgrau wie im Raster (ui/theme.py: WEEKEND_COLOR 235)
GRAY_DAY = (235 / 255.0, 235 / 255.0, 235 / 255.0)
WHITE = (1.0, 1.0, 1.0)
# Deckkraft "in Planung" wie im CellDelegate (GENERATED_ALPHA = 110 von 255)
PLANNING_ALPHA = 110 / 255.0


def _hex_rgb(hex_color: str) -> tuple[float, float, float]:
    hex_color = hex_color.lstrip("#")
    return (
        int(hex_color[0:2], 16) / 255.0,
        int(hex_color[2:4], 16) / 255.0,
        int(hex_color[4:6], 16) / 255.0,
    )


def _blend(hex_color: str, alpha: float,
           base: tuple[float, float, float]) -> colors.Color:
    """Farbe mit Deckkraft auf die Grundflaeche komponieren.

    Liefert eine deckende Farbe - so sieht das PDF exakt aus wie der
    Bildschirm, ohne Alpha-Artefakte am Tabellenraster."""
    r, g, b = _hex_rgb(hex_color)
    return colors.Color(
        r * alpha + base[0] * (1 - alpha),
        g * alpha + base[1] * (1 - alpha),
        b * alpha + base[2] * (1 - alpha),
    )


def _entry_hex(settings: AppSettings, key: str) -> str:
    return settings.entry_colors.get(key, "#9E9E9E")


def _is_gray_day(year: int, month: int, day: int) -> bool:
    return (dt_date(year, month, day).weekday() >= 5
            or holiday_name(year, month, day) is not None)


def _cell_content(plan: MonthPlan, settings: AppSettings, assistant, day: int,
                  base: tuple[float, float, float]):
    """Text, Hintergrundfarbe und Fettdruck einer Planzelle.

    Gleiche Logik wie CellDelegate.paint, nur ohne Kandidaten-Vorschlaege
    (der Ausdruck zeigt nur wirksame Zuteilungen)."""
    entries = [e for e in plan.schedule.get(day, [])
               if e.assistant_id == assistant.id and is_effective(e)]
    duty = next((e for e in entries if is_duty(e.shift_type)), None)
    oncall = next((e for e in entries
                   if e.shift_type == ShiftType.ON_CALL), None)

    entry = duty or oncall
    if entry is not None:
        text = SHIFT_LABELS.get(entry.shift_type, "")
        if duty is not None and oncall is not None:
            # Doppelbelegung (warnt der Validator) - beides zeigen
            text += "/RB"
        in_planning = (not entry.locked
                       and (entry.generated or (entry.candidate and entry.chosen)))
        alpha = PLANNING_ALPHA if in_planning else 1.0
        color = _blend(_entry_hex(settings, entry.shift_type.value), alpha, base)
        return text, color, not in_planning

    if is_on_vacation(assistant, day, plan.year, plan.month):
        return "U", _blend(_entry_hex(settings, "VACATION"), 1.0, base), False
    if is_blocked(assistant, day, plan.year, plan.month):
        return "X", _blend(_entry_hex(settings, "BLOCK"), 1.0, base), False
    return "", None, False


def _plan_table(plan: MonthPlan, settings: AppSettings,
                first_day: int, last_day: int, day_width: float) -> Table:
    """Eine Plantabelle fuer einen Tagesbereich (Zeile = Helfer)."""
    year, month = plan.year, plan.month
    days = list(range(first_day, last_day + 1))

    header = ["Assistent"]
    for day in days:
        weekday = WEEKDAYS_DE[dt_date(year, month, day).weekday()]
        # * = Tag hat eine Notiz (siehe Abschnitt "Notizen")
        note_mark = "*" if (plan.notes.get(day) or "").strip() else ""
        header.append(f"{day}{note_mark}\n{weekday}")
    data = [header]
    style_list = [
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 7),
        ("FONTSIZE", (0, 1), (-1, -1), 6),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
    ]

    # Wochenenden und Feiertage grau hinterlegen (ganze Spalte inkl. Kopf)
    gray = colors.Color(*GRAY_DAY)
    day_bases: dict[int, tuple[float, float, float]] = {}
    for col, day in enumerate(days, 1):
        if _is_gray_day(year, month, day):
            day_bases[day] = GRAY_DAY
            style_list.append(("BACKGROUND", (col, 0), (col, -1), gray))
        else:
            day_bases[day] = WHITE

    for row, assistant in enumerate(plan.assistants, 1):
        cells = [assistant.name]
        for col, day in enumerate(days, 1):
            text, color, bold = _cell_content(
                plan, settings, assistant, day, day_bases[day]
            )
            cells.append(text)
            if color is not None:
                style_list.append(("BACKGROUND", (col, row), (col, row), color))
            if bold and text:
                style_list.append(
                    ("FONTNAME", (col, row), (col, row), "Helvetica-Bold")
                )
        data.append(cells)

    table = Table(data, colWidths=[NAME_COL_WIDTH] + [day_width] * len(days))
    table.hAlign = "LEFT"
    table.setStyle(TableStyle(style_list))
    return table


def _legend_table(settings: AppSettings) -> Table:
    """Farb-Legende: ein Farbfeld je Eintragsart, wie im Farben-Dialog."""
    items = [
        ("FULL", "Tagesdienst (VOLL)"),
        ("HALF_MORNING", "Vormittag (VM)"),
        ("HALF_AFTERNOON", "Nachmittag (NM)"),
        ("ON_CALL", "Rufbereitschaft (RB)"),
        ("VACATION", "Urlaub (U)"),
        ("BLOCK", "Block (X)"),
    ]
    data = [["", label] for _key, label in items]
    style_list = [
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (0, -1), 0.5, colors.grey),
    ]
    for row, (key, _label) in enumerate(items):
        style_list.append(
            ("BACKGROUND", (0, row), (0, row),
             _blend(_entry_hex(settings, key), 1.0, WHITE))
        )
    table = Table(data, colWidths=[0.8 * cm, 6.0 * cm])
    table.hAlign = "LEFT"
    table.setStyle(TableStyle(style_list))
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
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Heading1"],
        fontSize=16,
        textColor=colors.black,
        spaceAfter=10,
    )
    body_style = ParagraphStyle(
        "CustomBody",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
    )

    # Monat in zwei Haelften, jede auf einer eigenen Seite - so bricht
    # keine Tabelle mitten durch und die Zellen bleiben gross genug
    half = math.ceil(days_in_month / 2)
    available_width = PAGE_SIZE[0] - 2 * MARGIN
    day_width = (available_width - NAME_COL_WIDTH) / half

    story = [
        Paragraph(
            f"Dienstplan {MONTHS_DE[month]} {year} - 1. Haelfte",
            title_style,
        ),
        Spacer(1, 0.3 * cm),
        _plan_table(plan, settings, 1, half, day_width),
        PageBreak(),
        Paragraph(
            f"Dienstplan {MONTHS_DE[month]} {year} - 2. Haelfte",
            title_style,
        ),
        Spacer(1, 0.3 * cm),
        _plan_table(plan, settings, half + 1, days_in_month, day_width),
        PageBreak(),
    ]

    # Seite 3: Zusammenfassung, Legende, Notizen, Feiertage
    story.append(Paragraph("Zusammenfassung", styles["Heading2"]))
    story.append(Spacer(1, 0.2 * cm))

    summary_data = [["Assistent", "Dienste gesamt", "VOLL", "VM", "NM", "RB"]]
    for assistant in plan.assistants:
        full = vm = nm = rb = 0
        for entries in plan.schedule.values():
            for e in entries:
                if e.assistant_id == assistant.id and is_effective(e):
                    if e.shift_type == ShiftType.FULL:
                        full += 1
                    elif e.shift_type == ShiftType.HALF_MORNING:
                        vm += 1
                    elif e.shift_type == ShiftType.HALF_AFTERNOON:
                        nm += 1
                    elif e.shift_type == ShiftType.ON_CALL:
                        rb += 1
        # Gewichtete Dienstzahl (VOLL=1, VM/NM=0,5); RB zaehlt separat
        total = full + 0.5 * (vm + nm)
        summary_data.append(
            [assistant.name, f"{total:g}", str(full), str(vm), str(nm), str(rb)]
        )

    summary_table = Table(summary_data, colWidths=[3.5 * cm] * 6)
    summary_table.hAlign = "LEFT"
    summary_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
    ]))
    story.append(summary_table)

    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph("Legende", styles["Heading2"]))
    story.append(Spacer(1, 0.2 * cm))
    story.append(_legend_table(settings))
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph(
        "Blasse Farbe = noch nicht fixiert (in Planung). "
        "Grau = Wochenende oder Feiertag (Bayern). "
        "* im Tageskopf = Tagesnotiz (siehe Notizen).",
        body_style,
    ))

    notes = sorted(
        (day, text.strip())
        for day, text in plan.notes.items()
        if (text or "").strip()
    )
    if notes:
        story.append(Spacer(1, 0.4 * cm))
        story.append(Paragraph("Notizen", styles["Heading2"]))
        story.append(Spacer(1, 0.2 * cm))
        for day, text in notes:
            story.append(Paragraph(
                f"{day:02d}.{month:02d}.: {escape(text)}", body_style
            ))

    month_holidays = sorted(
        (d, name) for d, name in bavarian_holidays(year).items()
        if d.month == month
    )
    if month_holidays:
        story.append(Spacer(1, 0.4 * cm))
        story.append(Paragraph("Feiertage", styles["Heading2"]))
        story.append(Spacer(1, 0.2 * cm))
        for d, name in month_holidays:
            story.append(Paragraph(f"{d.day:02d}.{month:02d}.: {name}", body_style))

    doc.build(story)
    return str(pdf_file)
