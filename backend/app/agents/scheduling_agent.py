"""Find interview times that fit interviewer calendars and local reservations."""

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def find_available_slots(
    *,
    time_min: datetime,
    time_max: datetime,
    duration_minutes: int,
    busy_intervals: list[tuple[datetime, datetime]],
    working_intervals: list[tuple[datetime, datetime]] | None = None,
    time_zone: str = "UTC",
    max_slots: int = 20,
) -> list[tuple[datetime, datetime]]:
    """Generate weekday work-hour slots free in calendars and local reservations."""
    if time_min.tzinfo is None or time_max.tzinfo is None:
        raise ValueError("Availability range must include time zones.")
    if time_max <= time_min:
        raise ValueError("Availability end must be after its start.")
    if duration_minutes < 15 or duration_minutes > 240:
        raise ValueError("Interview duration must be between 15 and 240 minutes.")
    if max_slots < 1:
        return []
    try:
        zone = ZoneInfo(time_zone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown calendar time zone: {time_zone}") from exc

    range_start = time_min.astimezone(timezone.utc)
    range_end = time_max.astimezone(timezone.utc)
    occupied = list(busy_intervals) + (working_intervals or [])
    duration = timedelta(minutes=duration_minutes)
    slots: list[tuple[datetime, datetime]] = []
    local_day = time_min.astimezone(zone).date()
    final_day = time_max.astimezone(zone).date()

    while local_day <= final_day and len(slots) < max_slots:
        if local_day.weekday() < 5:
            local_open = datetime.combine(local_day, time(9, 0), tzinfo=zone)
            local_close = datetime.combine(local_day, time(17, 0), tzinfo=zone)
            candidate = local_open
            while candidate + duration <= local_close and len(slots) < max_slots:
                start = candidate.astimezone(timezone.utc)
                end = (candidate + duration).astimezone(timezone.utc)
                if (
                    start >= range_start
                    and end <= range_end
                    and not any(
                        busy_start < end and busy_end > start
                        for busy_start, busy_end in occupied
                    )
                ):
                    slots.append((start, end))
                candidate += timedelta(minutes=30)
        local_day += timedelta(days=1)
    return slots
