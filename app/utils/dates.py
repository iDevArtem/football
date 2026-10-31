from datetime import datetime, time
from zoneinfo import ZoneInfo


def now_tz(tz_name: str) -> datetime:
    return datetime.now(ZoneInfo(tz_name))


def parse_date_time(date_raw: str, time_raw: str, tz_name: str) -> datetime:
    day = datetime.strptime(date_raw, "%Y-%m-%d").date()
    hour, minute = map(int, time_raw.split(":"))
    return datetime.combine(day, time(hour, minute), tzinfo=ZoneInfo(tz_name))
