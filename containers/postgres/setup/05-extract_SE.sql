CREATE OR REPLACE FUNCTION extract_SE(date DATE)
RETURNS INT AS $$
from datetime import date as dt

def _system_adjustment(system: str) -> int:
    systems = ("iso", "cdc")  # Monday, Sunday
    return systems.index(system.lower())

def _year_start(year: int, system: str) -> int:
    adjustment = _system_adjustment(system)
    mid_weekday = 3 - adjustment  # Sun is 6 .. Mon is 0
    jan1 = dt(year, 1, 1)
    jan1_ordinal = jan1.toordinal()
    jan1_weekday = jan1.weekday()
    week1_start_ordinal = jan1_ordinal - jan1_weekday - adjustment
    if jan1_weekday > mid_weekday:
        week1_start_ordinal += 7
    return week1_start_ordinal

def fromdate(date: dt, system: str = "cdc") -> int:
    if isinstance(date, str):
        date = dt.fromisoformat(date)
    year = date.year
    date_ordinal = date.toordinal()
    year_start_ordinal = _year_start(year, system)
    week = (date_ordinal - year_start_ordinal) // 7
    if week < 0:
        year -= 1
        year_start_ordinal = _year_start(year, system)
        week = (date_ordinal - year_start_ordinal) // 7
    elif week >= 52:
        year_start_ordinal = _year_start(year + 1, system)
        if date_ordinal >= year_start_ordinal:
            year += 1
            week = 0
    week += 1
    return int(str(year) + f"{week:02d}")

return fromdate(date, "cdc")
$$ LANGUAGE plpython3u;
