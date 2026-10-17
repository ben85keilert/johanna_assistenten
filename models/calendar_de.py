"""Deutsche Monats- und Wochentagsnamen (ASCII-Umschrift wie im ganzen Code)."""

MONTHS_DE = ["", "Januar", "Februar", "Maerz", "April", "Mai", "Juni",
             "Juli", "August", "September", "Oktober", "November", "Dezember"]
WEEKDAYS_DE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def month_label(year: int, month: int) -> str:
    """z. B. "Oktober 2026"."""
    return f"{MONTHS_DE[month]} {year}"
