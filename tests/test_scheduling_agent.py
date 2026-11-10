from datetime import datetime, timezone

import pytest

from app.agents.scheduling_agent import find_available_slots


def test_available_slots_exclude_busy_local_reservations_and_weekends() -> None:
    start = datetime(2030, 1, 4, 9, 0, tzinfo=timezone.utc)
    end = datetime(2030, 1, 7, 11, 0, tzinfo=timezone.utc)
    busy = [
        (
            datetime(2030, 1, 4, 9, 0, tzinfo=timezone.utc),
            datetime(2030, 1, 4, 9, 30, tzinfo=timezone.utc),
        )
    ]
    reservations = [
        (
            datetime(2030, 1, 4, 10, 0, tzinfo=timezone.utc),
            datetime(2030, 1, 4, 10, 30, tzinfo=timezone.utc),
        )
    ]

    slots = find_available_slots(
        time_min=start,
        time_max=end,
        duration_minutes=30,
        busy_intervals=busy,
        working_intervals=reservations,
        max_slots=100,
    )

    assert slots[:2] == [
        (
            datetime(2030, 1, 4, 9, 30, tzinfo=timezone.utc),
            datetime(2030, 1, 4, 10, 0, tzinfo=timezone.utc),
        ),
        (
            datetime(2030, 1, 4, 10, 30, tzinfo=timezone.utc),
            datetime(2030, 1, 4, 11, 0, tzinfo=timezone.utc),
        ),
    ]
    assert (
        datetime(2030, 1, 7, 9, 0, tzinfo=timezone.utc),
        datetime(2030, 1, 7, 9, 30, tzinfo=timezone.utc),
    ) in slots
    assert all(start.weekday() < 5 for start, _ in slots)
    assert all(
        not (busy_start < slot_end and busy_end > slot_start)
        for slot_start, slot_end in slots
        for busy_start, busy_end in busy + reservations
    )


def test_available_slots_validate_timezone_range_and_duration() -> None:
    start = datetime(2030, 1, 7, 9, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="time zones"):
        find_available_slots(
            time_min=start.replace(tzinfo=None),
            time_max=start,
            duration_minutes=30,
            busy_intervals=[],
        )
    with pytest.raises(ValueError, match="duration"):
        find_available_slots(
            time_min=start,
            time_max=start.replace(hour=17),
            duration_minutes=10,
            busy_intervals=[],
        )
