from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.reminders.selector import _is_due_for_reminder, find_due_reminder


TZ = ZoneInfo("Europe/London")


@pytest.mark.parametrize(
    ("clock_time", "now_hour", "now_minute", "expected"),
    [
        ("07:30", 7, 0, True),    # 30 minutes away
        ("09:15", 8, 45, True),   # 30 minutes away
        ("09:17", 8, 50, True),   # 27 minutes away
        ("09:17", 8, 45, False),  # 32 minutes away
        (None, 7, 0, False),      # no clock_time is never invented
    ],
)
def test_due_window_is_25_to_30_minutes(clock_time, now_hour, now_minute, expected):
    now = datetime(2026, 10, 23, now_hour, now_minute, tzinfo=TZ)

    assert _is_due_for_reminder({"clock_time": clock_time}, now) is expected


def test_walk_due_in_30_minutes_is_selected():
    now = datetime(
        2026,
        10,
        23,
        7,
        0,
        tzinfo=TZ,
    )

    tasks = [
        {
            "occurrence_id": "walk#2026-10-23#1",
            "title": "Short walk",
            "clock_time": "07:30",
            "time_of_day_label": "morning",
            "occurrence_number": 1,
            "status": "pending",
            "needs_confirmation": False,
        }
    ]

    reminder = find_due_reminder(
        tasks=tasks,
        medications=[],
        now=now,
    )

    assert reminder is not None
    assert reminder["occurrence_id"] == "walk#2026-10-23#1"


def test_different_patient_time_is_dynamic():
    now = datetime(
        2026,
        10,
        23,
        8,
        45,
        tzinfo=TZ,
    )

    tasks = [
        {
            "occurrence_id": "walk#2026-10-23#1",
            "title": "Short walk",
            "clock_time": "09:15",
            "time_of_day_label": "morning",
            "occurrence_number": 1,
            "status": "pending",
            "needs_confirmation": False,
        }
    ]

    reminder = find_due_reminder(
        tasks,
        [],
        now,
    )

    assert reminder is not None
    assert reminder["clock_time"] == "09:15"


def test_completed_occurrence_is_not_reminded():
    now = datetime(
        2026,
        10,
        23,
        7,
        0,
        tzinfo=TZ,
    )

    tasks = [
        {
            "occurrence_id": "walk#1",
            "title": "Walk",
            "clock_time": "07:30",
            "status": "completed",
        }
    ]

    assert find_due_reminder(tasks, [], now) is None


def test_prn_medication_is_not_reminded():
    now = datetime(
        2026,
        10,
        23,
        7,
        0,
        tzinfo=TZ,
    )

    medications = [
        {
            "occurrence_id": "codeine#1",
            "name": "Codeine",
            "clock_time": "07:30",
            "status": "pending",
            "as_needed": True,
        }
    ]

    assert find_due_reminder(
        [],
        medications,
        now,
    ) is None


def test_needs_confirmation_is_not_reminded():
    now = datetime(
        2026,
        10,
        23,
        7,
        0,
        tzinfo=TZ,
    )

    tasks = [
        {
            "occurrence_id": "unsafe#1",
            "title": "Unclear task",
            "clock_time": "07:30",
            "status": "pending",
            "needs_confirmation": True,
        }
    ]

    assert find_due_reminder(
        tasks,
        [],
        now,
    ) is None


def test_missing_clock_time_is_not_invented():
    now = datetime(
        2026,
        10,
        23,
        7,
        0,
        tzinfo=TZ,
    )

    tasks = [
        {
            "occurrence_id": "task#1",
            "title": "Exercise",
            "time_of_day_label": "morning",
            "status": "pending",
        }
    ]

    assert find_due_reminder(
        tasks,
        [],
        now,
    ) is None