from pathlib import Path
import math
import calendar
from datetime import date as dt_date

from reportlab.lib import pagesizes
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors

from models import MonthPlan, ShiftType

SHIFT_LABELS = {
    ShiftType.FULL: "VOLL",
    ShiftType.HALF_MORNING: "VM",
    ShiftType.HALF_AFTERNOON: "NM",
    ShiftType.ON_CALL: "RB",
}

PAGE_SIZE = pagesizes.landscape(pagesizes.A4)
MARGIN = 0.5 * cm
NAME_COL_WIDTH = 2.5 * cm


def _hex_to_color(hex_color: str, alpha: float = 1.0) -> colors.Color:
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16) / 255.0
    g = int(hex_color[2:4], 16) / 255.0
    b = int(hex_color[4:6], 16) / 255.0
    return colors.Color(r, g, b, alpha=alpha)


def _plan_table(plan: MonthPlan, first_day: int, last_day: int, day_width: float) -> Table:
    """Eine Plantabelle fuer einen Tagesbereich (Zeile = Helfer)."""
    year, month = plan.year, plan.month
    days = range(first_day, last_day + 1)

    header = ["Assistent"]
    for day in days:
        weekday = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"][dt_date(year, month, day).weekday()]
        header.append(f"{day}\n{weekday}")
    data = [header]

    for assistant in plan.assistants:
        row = [assistant.name]
        for day in days:
            entries = plan.schedule.get(day, [])
            matching = [e for e in entries if e.assistant_id == assistant.id]
            row.append(SHIFT_LABELS.get(matching[0].shift_type, "") if matching else "")
        data.append(row)

    table = Table(data, colWidths=[NAME_COL_WIDTH] + [day_width] * len(list(days)))
    table.hAlign = "LEFT"

    style_list = [
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 7),
        ("FONTSIZE", (0, 1), (-1, -1), 6),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
    ]

    # Wochenenden grau hinterlegen
    for col, day in enumerate(days, 1):
        if dt_date(year, month, day).weekday() >= 5:
            style_list.append(
                ("BACKGROUND", (col, 0), (col, -1), colors.Color(0.92, 0.92, 0.92))
            )

    # Helferfarben auf belegte Zellen
    for row, assistant in enumerate(plan.assistants, 1):
        try:
            color = _hex_to_color(assistant.color, alpha=0.7)
        except ValueError:
            continue
        for col, day in enumerate(days, 1):
            entries = plan.schedule.get(day, [])
            if any(e.assistant_id == assistant.id for e in entries):
                style_list.append(("BACKGROUND", (col, row), (col, row), color))

    table.setStyle(TableStyle(style_list))
    return table


def export_pdf(plan: MonthPlan, folder: str | Path) -> str:
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
    months_de = ["", "Januar", "Februar", "Maerz", "April", "Mai", "Juni",
                 "Juli", "August", "September", "Oktober", "November", "Dezember"]

    story = [
        Paragraph(f"Dienstplan {months_de[month]} {year}", title_style),
        Spacer(1, 0.3 * cm),
    ]

    # Monat in zwei Haelften untereinander, damit alles auf die Seite passt
    half = math.ceil(days_in_month / 2)
    available_width = PAGE_SIZE[0] - 2 * MARGIN
    day_width = (available_width - NAME_COL_WIDTH) / half

    story.append(_plan_table(plan, 1, half, day_width))
    story.append(Spacer(1, 0.4 * cm))
    story.append(_plan_table(plan, half + 1, days_in_month, day_width))

    # Zusammenfassung
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph("Zusammenfassung", styles["Heading2"]))
    story.append(Spacer(1, 0.2 * cm))

    summary_data = [["Assistent", "Dienste gesamt", "VOLL", "VM", "NM", "RB"]]
    for assistant in plan.assistants:
        full = vm = nm = rb = 0
        for entries in plan.schedule.values():
            for e in entries:
                if e.assistant_id == assistant.id:
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
    summary_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
    ]))
    story.append(summary_table)

    doc.build(story)
    return str(pdf_file)
