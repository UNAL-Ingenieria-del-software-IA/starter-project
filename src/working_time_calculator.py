
"""Cálculo de tiempo hábil según el calendario laboral colombiano."""

from datetime import date, datetime, time, timedelta, timezone

from src.holidays import is_colombian_holiday

# Colombia utiliza UTC-05:00 durante todo el año.
# Se utiliza un desplazamiento fijo para evitar depender de tzdata.
BOGOTA_TZ = timezone(timedelta(hours=-5), name="COT")

WORK_START = time(8, 0)
WORK_END = time(18, 0)


def to_bogota(value: datetime) -> datetime:
    """Normaliza una fecha a la hora local de Colombia.

    Las fechas sin zona horaria se interpretan como hora local de Bogotá.
    Las fechas con zona horaria se convierten a UTC-05:00.
    """
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=BOGOTA_TZ)

    return value.astimezone(BOGOTA_TZ)


def is_working_day(day: date) -> bool:
    """Determina si una fecha es un día laboral colombiano."""
    return day.weekday() < 5 and not is_colombian_holiday(day)


def calculate_working_minutes(
    start_time: datetime,
    end_time: datetime,
) -> int:
    """Calcula los minutos efectivos dentro del horario laboral.

    Recorre cada día del intervalo y acumula únicamente la
    intersección con la jornada laboral de 08:00 a 18:00.
    """
    start = to_bogota(start_time)
    end = to_bogota(end_time)

    if end < start:
        raise ValueError("El tiempo final no puede ser anterior al inicial.")

    if end == start:
        return 0

    total_seconds = 0
    current_day = start.date()

    while current_day <= end.date():
        if is_working_day(current_day):
            work_start = datetime.combine(
                current_day, WORK_START, tzinfo=BOGOTA_TZ
            )
            work_end = datetime.combine(
                current_day, WORK_END, tzinfo=BOGOTA_TZ
            )

            interval_start = max(start, work_start)
            interval_end = min(end, work_end)

            if interval_end > interval_start:
                total_seconds += (
                    interval_end - interval_start
                ).total_seconds()

        current_day += timedelta(days=1)

    return int(total_seconds // 60)
