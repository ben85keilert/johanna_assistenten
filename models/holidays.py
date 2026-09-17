"""Gesetzliche Feiertage in Bayern - rein rechnerisch, ohne Abhaengigkeiten.

Die Feiertage werden im Plan, im Urlaubs-Kalender und im PDF-Export wie
Wochenenden grau hinterlegt (reine Anzeige - die Planungslogik behandelt
Feiertage nicht anders als normale Tage). Mariae Himmelfahrt gilt im
ueberwiegend katholischen Bayern und ist enthalten; das Augsburger
Friedensfest (8.8., nur Stadt Augsburg) nicht.
"""
from datetime import date, timedelta
from functools import lru_cache


def easter_sunday(year: int) -> date:
    """Ostersonntag nach der anonymen Gregorianischen (Gauss-)Formel."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


@lru_cache(maxsize=None)
def bavarian_holidays(year: int) -> dict[date, str]:
    """Alle 13 gesetzlichen Feiertage Bayerns des Jahres (Datum -> Name)."""
    easter = easter_sunday(year)
    return {
        date(year, 1, 1): "Neujahr",
        date(year, 1, 6): "Heilige Drei Koenige",
        easter - timedelta(days=2): "Karfreitag",
        easter + timedelta(days=1): "Ostermontag",
        date(year, 5, 1): "Tag der Arbeit",
        easter + timedelta(days=39): "Christi Himmelfahrt",
        easter + timedelta(days=50): "Pfingstmontag",
        easter + timedelta(days=60): "Fronleichnam",
        date(year, 8, 15): "Mariae Himmelfahrt",
        date(year, 10, 3): "Tag der Deutschen Einheit",
        date(year, 11, 1): "Allerheiligen",
        date(year, 12, 25): "1. Weihnachtstag",
        date(year, 12, 26): "2. Weihnachtstag",
    }


def holiday_name(year: int, month: int, day: int) -> str | None:
    """Name des Feiertags an diesem Tag, sonst None."""
    return bavarian_holidays(year).get(date(year, month, day))
