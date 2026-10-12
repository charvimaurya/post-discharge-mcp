"""
The reminder is consistent: the same time gives the same reminder, a waiting
reminder is never replaced by a reload, and "already sent" never brings in an
item that is outside its own window.

The real engine, reminder handler, bridge route and reset script run against
an in-memory patient record. Demo clock, 23 October 2026.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest
from starlette.testclient import TestClient

from app import web_bridge
from app.reminders.engine import choose_checkin, pending_is_valid
from lambdas.reminder_checker import handler as checker
from scripts import reset_demo_patient as reset


LONDON = ZoneInfo("Europe/London")
REAL_NOW = datetime(2026, 10, 12, 9, 0, tzinfo=timezone.utc)
WALK_1 = "walk#2026-10-23#1"
WALK_KEY = f"2026-10-23#{WALK_1}"
MEDICINES_KEY = "2026-10-23#medicine#morning"


def at(hhmm: str) -> datetime:
    hour, minute = map(int, hhmm.split(":"))
    return datetime(2026, 10, 23, hour, minute, tzinfo=LONDON)


def plan():
    tasks = [
        {"occurrence_id": f"walk#2026-10-23#{n}", "task_id": "walk", "clock_time": clock, "occurrence_number": n,
         "description": "Walking: one short walk of 5 to 10 minutes, twice a day, using your walking frame.",
         "status": "pending"} for n, clock in [(1, "07:30"), (2, "15:00")]
    ]
    medications = [
        {"occurrence_id": f"{med}#2026-10-23#{n}", "medication_id": med, "name": name, "dose": dose,
         "instructions": "Take the morning dose after breakfast.", "time_of_day_label": slot,
         "occurrence_number": n, "status": "pending"}
        for med, name, dose, slots in [
            ("para", "Paracetamol", "2 tablets", ["morning", "midday", "evening", "bedtime"]),
            ("apix", "Apixaban", "1 tablet", ["morning", "evening"]),
        ]
        for n, slot in enumerate(slots, start=1)
    ]
    return tasks, medications


def choose(state, tasks, medications, now):
    return choose_checkin(state, tasks, medications, now, real_now_utc=REAL_NOW, first_name="Margaret")


# ---------- The engine: windows, fixed priority, sticky ----------

def test_at_0700_the_only_candidate_is_the_0730_walk():
    tasks, medications = plan()

    decision = choose({}, tasks, medications, at("07:00"))

    assert [c.checkin_id for c in decision.candidates] == [WALK_KEY]
    assert decision.checkin.type == "reminder" and decision.checkin.occurrence_id == WALK_1


@pytest.mark.parametrize("clock, expected", [
    ("06:59", None), ("07:00", WALK_KEY), ("07:15", WALK_KEY), ("07:30", WALK_KEY),
])
def test_a_walk_is_a_candidate_from_30_minutes_before_until_its_time(clock, expected, monkeypatch):
    monkeypatch.setenv("QUIET_HOURS_END", "06:00")
    tasks, medications = plan()

    walks = [c.checkin_id for c in choose({}, tasks, medications, at(clock)).candidates if c.type == "reminder"]

    assert walks == ([expected] if expected else [])


def test_the_walk_window_is_over_at_0731():
    tasks, medications = plan()

    assert not [c for c in choose({}, tasks, medications, at("07:31")).candidates if c.type == "reminder"]


@pytest.mark.parametrize("clock", ["07:00", "07:15", "07:29"])
def test_the_medicines_reminder_never_appears_before_0730(clock):
    tasks, medications = plan()
    # Even with the walk already sent and answered: nothing else is brought in.
    state = {"last_checkin_key": WALK_KEY, "checkins_today_date": "2026-10-23", "checkins_today_ids": [WALK_KEY]}

    decision = choose(state, tasks, medications, at(clock))

    assert decision.checkin is None and decision.reason == "already_reminded"
    assert not [c for c in decision.candidates if c.type == "medicine"]


def test_at_0735_the_medicines_reminder_may_appear():
    tasks, medications = plan()

    checkin = choose({}, tasks, medications, at("07:35")).checkin

    assert checkin.type == "medicine" and checkin.checkin_id == MEDICINES_KEY
    assert checkin.occurrence_ids == ["para#2026-10-23#1", "apix#2026-10-23#1"]
    assert checkin.text == (
        "Good morning, Margaret. I hope you slept well. "
        "Next is your paracetamol and blood thinner, after breakfast."
    )


def test_the_same_time_always_gives_the_same_reminder():
    tasks, medications = plan()

    for clock in ("07:00", "07:35", "09:30", "14:45"):
        chosen = {choose({}, tasks, medications, at(clock)).checkin.checkin_id for _ in range(5)}
        assert len(chosen) == 1


def test_fixed_priority_when_windows_overlap():
    tasks, medications = plan()

    # 14:45: the afternoon walk's window, and the midday paracetamol has been missed since 13:30.
    decision = choose({}, tasks, medications, at("14:45"))

    assert [c.type for c in decision.candidates] == ["missed_dose", "reminder"]
    assert decision.checkin.type == "missed_dose"


def test_a_waiting_reminder_is_not_replaced_while_it_is_valid():
    tasks, medications = plan()
    pending = choose({}, tasks, medications, at("07:00")).checkin.as_pending("2026-10-23", at("07:00"))

    decision = choose({"pending_checkin": pending}, tasks, medications, at("07:20"))

    assert decision.checkin is None and decision.reason == "checkin_waiting" and decision.expired is False


def test_a_waiting_reminder_ends_with_its_window_or_when_its_item_is_ticked():
    tasks, medications = plan()
    pending = choose({}, tasks, medications, at("07:00")).checkin.as_pending("2026-10-23", at("07:00"))

    assert pending["expires_at"] == at("07:30").isoformat()
    assert pending_is_valid(pending, tasks, medications, at("07:30"))
    assert not pending_is_valid(pending, tasks, medications, at("07:35"))

    tasks[0]["status"] = "completed"
    assert not pending_is_valid(pending, tasks, medications, at("07:10"))


def test_a_reminder_saved_before_windows_were_recorded_stays_until_she_replies():
    tasks, medications = plan()
    old = {"checkin_id": WALK_KEY, "occurrence_id": WALK_1, "type": "reminder", "text": "Good morning."}

    assert pending_is_valid(old, tasks, medications, at("11:00"))


# ---------- Handler, bridge and reset together ----------

@pytest.fixture
def patient(monkeypatch):
    """One in-memory patient record behind the real handler, the bridge route and the reset script."""

    tasks, medications = plan()
    record = {"patient_id": "demo_patient_001", "first_name": "Margaret", "timezone": "Europe/London",
              "tasks": tasks, "medications": medications}

    def save(patient_id, pending, key, *, today=None, max_per_day=None, scheduled_checkins=None):
        if record.get("last_checkin_key") == key or key in (record.get("checkins_today_ids") or []):
            return False
        if record.get("pending_checkin"):
            return False
        record.update(pending_checkin=pending, last_checkin_key=key, checkins_today_date=today,
                      checkins_today_ids=[*(record.get("checkins_today_ids") or []), key])
        return True

    monkeypatch.setattr(checker, "get_recovery_state", lambda patient_id: dict(record))
    monkeypatch.setattr(checker, "get_today_tasks", lambda patient_id, date: [dict(t) for t in record["tasks"]])
    monkeypatch.setattr(checker, "get_medications", lambda patient_id, date: [dict(m) for m in record["medications"]])
    monkeypatch.setattr(checker, "save_pending_checkin", save)
    monkeypatch.setattr(checker, "clear_pending_checkin", lambda patient_id: record.pop("pending_checkin", None))
    monkeypatch.setattr(checker, "system_now_utc", lambda: REAL_NOW)
    monkeypatch.setattr(reset, "get_recovery_state", lambda patient_id: record)
    monkeypatch.setattr(reset, "save_recovery_state", lambda state: None)
    monkeypatch.delenv("LOCAL_REMINDER_LOOP", raising=False)

    client = TestClient(web_bridge.app)

    def check(clock: str) -> dict:
        monkeypatch.setenv("DEMO_FIXED_NOW", f"2026-10-23T{clock}:00+01:00")
        response = client.post("/reminders/check")
        assert response.status_code == 200
        return response.json()

    def reply():
        # What the bridge does after she answers: the reminder is cleared, the key is kept.
        record.pop("pending_checkin", None)

    record_api = type("Patient", (), {})()
    record_api.record, record_api.check, record_api.reply = record, check, reply
    record_api.reset = lambda: reset.reset_recovery_state("demo_patient_001")
    return record_api


def test_five_checks_at_0700_give_the_same_reminder(patient):
    results = [patient.check("07:00") for _ in range(5)]

    assert results[0]["created"] is True
    assert [r["pending_checkin"]["checkin_id"] for r in results] == [WALK_KEY] * 5
    assert [r.get("reason") for r in results[1:]] == ["checkin_waiting"] * 4
    # Returned unchanged, not rebuilt.
    assert all(r["pending_checkin"] == results[0]["pending_checkin"] for r in results)
    assert "walk" in results[0]["pending_checkin"]["text"] and "paracetamol" not in results[0]["pending_checkin"]["text"]


def test_after_she_replies_at_0700_there_is_no_new_reminder(patient):
    patient.check("07:00")
    patient.reply()

    for _ in range(3):
        result = patient.check("07:00")
        assert result == {"created": False, "reason": "already_reminded"}

    assert "pending_checkin" not in patient.record


def test_at_0735_the_walk_reminder_ends_and_the_medicines_reminder_may_appear(patient):
    patient.check("07:00")

    result = patient.check("07:35")

    assert result["created"] is True
    assert result["pending_checkin"]["checkin_id"] == MEDICINES_KEY and result["pending_checkin"]["type"] == "medicine"
    # And that one is sticky too.
    assert patient.check("07:40")["pending_checkin"]["checkin_id"] == MEDICINES_KEY


def test_a_ticked_item_clears_its_reminder_and_nothing_replaces_it_at_0710(patient):
    patient.check("07:00")
    patient.record["tasks"][0]["status"] = "completed"

    result = patient.check("07:10")

    assert result["created"] is False and "pending_checkin" not in result
    assert "pending_checkin" not in patient.record


def test_reset_starts_fresh_and_0700_shows_the_walk_again(patient):
    patient.check("07:00")
    patient.reply()
    assert patient.check("07:00")["created"] is False
    patient.record["scheduled_checkins"] = [{"checkin_id": "x", "due_at": "2026-10-23T11:00:00+01:00", "text": "t"}]

    patient.reset()

    for field in ("last_checkin_key", "scheduled_checkins", "checkins_today_ids", "checkins_today_date", "last_chat_at"):
        assert field not in patient.record
    assert not patient.record.get("pending_checkin")

    result = patient.check("07:00")
    assert result["created"] is True and result["pending_checkin"]["checkin_id"] == WALK_KEY
