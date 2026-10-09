from datetime import datetime
from zoneinfo import ZoneInfo

from app.reminders.text import build_reminder_text


def test_margaret_walk_reminder_text():
    now = datetime(
        2026,
        10,
        23,
        7,
        0,
        tzinfo=ZoneInfo("Europe/London"),
    )

    item = {
        "item_type": "task",
        "title": "Short walk",
        "time_of_day_label": "morning",
        "clock_time": "07:30",
    }

    text = build_reminder_text(
        "Margaret",
        item,
        now,
    )

    assert "Margaret" in text
    assert "morning walk" in text
    assert "half past seven" in text