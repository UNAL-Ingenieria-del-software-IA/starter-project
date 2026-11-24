
"""Generación dinámica de festivos nacionales de Colombia."""

from datetime import date, timedelta
from functools import lru_cache
from typing import Set


def _easter_sunday(year: int) -> date:
    """Calcula el Domingo de Pascua mediante el algoritmo gregoriano."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    weekday_offset = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * weekday_offset) // 451

    month = (h + weekday_offset - 7 * m + 114) // 31
    day = ((h + weekday_offset - 7 * m + 114) % 31) + 1

    return date(year, month, day)


def _next_monday(holiday: date) -> date:
    """Traslada un festivo al lunes siguiente, si corresponde."""
    return holiday + timedelta(days=(7 - holiday.weekday()) % 7)


@lru_cache(maxsize=None)
def colombian_holidays(year: int) -> frozenset[date]:
    """Genera los festivos nacionales colombianos para un año.

    Aplica la Ley 51 de 1983 (Ley Emiliani), incluyendo
    festivos trasladables y celebraciones religiosas.
    """
    holidays: Set[date] = set()

    # Festivos de fecha fija que no se trasladan.
    fixed_holidays = [
        (1, 1),    # Año Nuevo
        (5, 1),    # Día del Trabajo
        (7, 20),   # Independencia de Colombia
        (8, 7),    # Batalla de Boyacá
        (12, 8),   # Inmaculada Concepción
        (12, 25),  # Navidad
    ]

    holidays.update(date(year, month, day) for month, day in fixed_holidays)

    # Festivos de fecha fija trasladables al lunes.
    movable_fixed_holidays = [
        (1, 6),    # Reyes Magos
        (3, 19),   # San José
        (6, 29),   # San Pedro y San Pablo
        (8, 15),   # Asunción de la Virgen
        (10, 12),  # Día de la Raza
        (11, 1),   # Todos los Santos
        (11, 11),  # Independencia de Cartagena
    ]

    holidays.update(
        _next_monday(date(year, month, day))
        for month, day in movable_fixed_holidays
    )

    # Festivos religiosos calculados a partir de Pascua.
    easter = _easter_sunday(year)

    # Jueves y Viernes Santo no se trasladan.
    holidays.add(easter - timedelta(days=3))
    holidays.add(easter - timedelta(days=2))

    # Celebraciones religiosas trasladables al lunes.
    religious_holidays = [
        easter + timedelta(days=39),  # Ascensión
        easter + timedelta(days=60),  # Corpus Christi
        easter + timedelta(days=68),  # Sagrado Corazón
    ]

    holidays.update(_next_monday(day) for day in religious_holidays)

    return frozenset(holidays)


def is_colombian_holiday(day: date) -> bool:
    """Indica si una fecha corresponde a un festivo nacional."""
    return day in colombian_holidays(day.year)
