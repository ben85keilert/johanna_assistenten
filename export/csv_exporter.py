import csv
from pathlib import Path
from models import MonthPlan, ShiftType
import calendar


def export_csv(plan: MonthPlan, folder: str | Path) -> tuple[str, str]:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)

    year, month = plan.year, plan.month
    days_in_month = calendar.monthrange(year, month)[1]

    plan_file = folder / f"plan_{year}_{month:02d}.csv"
    summary_file = folder / f"zusammenfassung_{year}_{month:02d}.csv"

    # Plan-Datei
    with open(plan_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        header = ["Assistent"]
        for day in range(1, days_in_month + 1):
            header.append(f"{day}")
        writer.writerow(header)

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
                    elif entry.shift_type == ShiftType.HALF_AFTERNOON:
                        row.append("NM")
                    elif entry.shift_type == ShiftType.ON_CALL:
                        row.append("RB")
                    else:
                        row.append("")
                else:
                    row.append("")
            writer.writerow(row)

    # Zusammenfassung
    with open(summary_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Assistent", "Dienste gesamt", "VOLL", "VM", "NM", "RB"])

        for assistant in plan.assistants:
            full_count = 0
            vm_count = 0
            nm_count = 0
            rb_count = 0

            for entries in plan.schedule.values():
                for e in entries:
                    if e.assistant_id == assistant.id:
                        if e.shift_type == ShiftType.FULL:
                            full_count += 1
                        elif e.shift_type == ShiftType.HALF_MORNING:
                            vm_count += 1
                        elif e.shift_type == ShiftType.HALF_AFTERNOON:
                            nm_count += 1
                        elif e.shift_type == ShiftType.ON_CALL:
                            rb_count += 1

            # Gewichtete Dienstzahl (VOLL=1, VM/NM=0,5); RB zaehlt separat
            total = full_count + 0.5 * (vm_count + nm_count)
            writer.writerow(
                [assistant.name, f"{total:g}", full_count, vm_count, nm_count, rb_count]
            )

    return str(plan_file), str(summary_file)
