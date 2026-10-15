"""A second visit the same day says "Welcome back" and how far she has got, never "slept well" again."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.agent.next_up import build_opening_message
from app.reminders.text import build_return_greeting, is_or_are

NOW = datetime(2026, 10, 23, 7, 0, tzinfo=ZoneInfo("Europe/London"))


def test_welcome_back_with_progress():
    assert build_return_greeting("Margaret", 3, 13) == "Welcome back, Margaret. You've done 3 of 13 so far."


def test_welcome_back_with_nothing_done_yet():
    assert build_return_greeting("Margaret", 0, 13) == "Welcome back, Margaret."


def test_welcome_back_when_everything_is_done():
    assert build_return_greeting(None, 13, 13) == "Welcome back. You've done everything for today."


def test_returning_counts_completed_tasks_and_medicines():
    tasks = [{"title": "Knee exercises", "description": "Knee exercises", "status": "completed"},
             {"title": "Knee exercises", "description": "Knee exercises", "status": "pending"}]
    message = build_opening_message("Margaret", tasks, [], NOW, returning=True)

    assert message.startswith("Welcome back, Margaret. You've done 1 of 2 so far.")
    assert "slept well" not in message


def test_first_visit_is_unchanged():
    assert build_opening_message("Margaret", [], [], NOW) == "Good morning, Margaret. I hope you slept well."


@pytest.mark.parametrize("spoken, verb", [
    ("your knee exercises", "are"),
    ("your morning walk", "is"),
    ("your dressing", "is"),
    ("your ice pack on the knee", "is"),
    ("your breathing exercises, 10 minutes", "are"),
])
def test_next_is_or_are(spoken, verb):
    assert is_or_are(spoken) == verb
