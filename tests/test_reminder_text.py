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

    assert text == (
        "Good morning, Margaret. I hope you slept well. "
        "You have about thirty minutes until your morning walk, "
        "at half past seven."
    )


def test_later_reminders_do_not_mention_sleep():
    now = datetime(2026, 10, 23, 14, 30, tzinfo=ZoneInfo("Europe/London"))

    item = {
        "item_type": "task",
        "title": "Short walk",
        "time_of_day_label": "afternoon",
        "clock_time": "15:00",
    }

    text = build_reminder_text("Margaret", item, now)

    assert text.startswith("Good afternoon, Margaret. I hope you're doing well.")
    assert "slept" not in text


def test_walk_with_clock_time_but_no_time_of_day_word():
    # Margaret's real plan: the walk has clock_time 07:30 and no
    # time_of_day_label, and is described in full from the letter.
    now = datetime(2026, 10, 23, 7, 0, tzinfo=ZoneInfo("Europe/London"))

    item = {
        "item_type": "task",
        "description": (
            "Walking: one short walk of 5 to 10 minutes, twice a day, "
            "using your walking frame."
        ),
        "time_of_day_label": None,
        "clock_time": "07:30",
    }

    text = build_reminder_text("Margaret", item, now)

    assert text == (
        "Good morning, Margaret. I hope you slept well. "
        "You have about thirty minutes until your morning walk, "
        "at half past seven."
    )


def test_no_name_means_no_stand_in_word():
    now = datetime(2026, 10, 23, 7, 0, tzinfo=ZoneInfo("Europe/London"))
    item = {"item_type": "task", "title": "Short walk", "time_of_day_label": "morning", "clock_time": "07:30"}

    text = build_reminder_text(None, item, now)

    assert text.startswith("Good morning. I hope you slept well.")
    assert "there" not in text
