from pathlib import Path
from reportlab.lib import pagesizes
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from models import MonthPlan, ShiftType
import calendar
from datetime import date as dt_date


def _hex_to_rgb_reportlab(hex_color: str) -> tuple:
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16) / 255.0
    g = int(hex_color[2:4], 16) / 255.0
    b = int(hex_color[4:6], 16) / 255.0
    return (r, g, b)


def export_pdf(plan: MonthPlan, folder: str | Path) -> str:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)

    year, month = plan.year, plan.month
    days_in_month = calendar.monthrange(year, month)[1]

    pdf_file = folder / f"plan_{year}_{month:02d}.pdf"

    doc = SimpleDocTemplate(
        str(pdf_file),
        pagesize=pagesizes.landscape(pagesizes.A4),
        topMargin=0.5*cm,
        bottomMargin=0.5*cm,
        leftMargin=0.5*cm,
        rightMargin=0.5*cm,
    )

    story = []

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
    title = Paragraph(
        f"Dienstplan {months_de[month]} {year}",
        title_style
    )
    story.append(title)
    story.append(Spacer(1, 0.3*cm))

    # Plan-Tabelle
    data = []

    # Header
    header = ["Assistent"]
    for day in range(1, days_in_month + 1):
        d = dt_date(year, month, day)
        weekday = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"][d.weekday()]
        header.append(f"{day}\n{weekday}")
    data.append(header)

    # Daten
    for assistant in plan.assistants:
        row = [assistant.name]
        for day in range(1, days_in_month + 1):
            entries = plan.schedule.get(day, [])
            matching = [e for e in entries if e.assistant_id == assistant.id]
            if matching:
                entry = matching[0]
                if entry.shift_type == ShiftType.FULL:
                    row.append("VOLL")
                elif entry.shift_type == ShiftType.HALF_MORNING:
                    row.append("VM")
                else:
                    row.append("NM")
            else:
                row.append("")
        data.append(row)

    table = Table(data, colWidths=[2*cm] + [1.2*cm] * days_in_month)

    # Styles
    style_list = [
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 7),
        ("FONTSIZE", (0, 1), (-1, -1), 6),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
    ]

    # Farben fuer Assistenten
    for row, assistant in enumerate(plan.assistants, 1):
        try:
            rgb = _hex_to_rgb_reportlab(assistant.color)
            for col in range(1, days_in_month + 1):
                d = dt_date(year, month, col)
                entries = plan.schedule.get(col, [])
                matching = [e for e in entries if e.assistant_id == assistant.id]
                if matching:
                    style_list.append(
                        ("BACKGROUND", (col, row), (col, row), colors.Color(*rgb, alpha=0.7))
                    )
        except:
            pass

    # Wochenende Hintergrund
    for col in range(1, days_in_month + 1):
        d = dt_date(year, month, col)
        if d.weekday() >= 5:
            style_list.append(
                ("BACKGROUND", (col, 0), (col, -1), colors.Color(0.9, 0.9, 0.9, alpha=0.3))
            )

    table.setStyle(TableStyle(style_list))
    story.append(table)

    # Zusammenfassung
    story.append(Spacer(1, 0.5*cm))
    summary_title = Paragraph("Zusammenfassung", styles["Heading2"])
    story.append(summary_title)
    story.append(Spacer(1, 0.2*cm))

    summary_data = [["Assistent", "Dienste gesamt", "VOLL", "VM", "NM"]]
    for assistant in plan.assistants:
        total = 0
        full_count = 0
        vm_count = 0
        nm_count = 0

        for entries in plan.schedule.values():
            for e in entries:
                if e.assistant_id == assistant.id:
                    total += 1
                    if e.shift_type == ShiftType.FULL:
                        full_count += 1
                    elif e.shift_type == ShiftType.HALF_MORNING:
                        vm_count += 1
                    else:
                        nm_count += 1

        summary_data.append([assistant.name, str(total), str(full_count), str(vm_count), str(nm_count)])

    summary_table = Table(summary_data, colWidths=[4*cm] * 5)
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
