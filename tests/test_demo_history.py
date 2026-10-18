"""Demo history for past days: what the weekly dashboard and day details show from it."""
from datetime import datetime

import pytest

from app import demo_history
from app.mcp.tools import recovery_day, week

NOW = datetime.fromisoformat("2026-10-23T07:00:00+01:00")
PATIENT = demo_history.PATIENT_ID


def _occurrences(day):
    """Shaped like get_medications / get_today_tasks for Margaret's plan on that date."""
    meds = [("med_para", "Paracetamol", "2 tablets", label, n) for n, label in enumerate(("morning", "midday", "evening", "bedtime"), 1)]
    meds += [("med_apix", "Apixaban", "1 tablet", label, n) for n, label in enumerate(("morning", "evening"), 1)]
    medications = [{"occurrence_id": f"{i}#{day}#{n}", "name": name, "dose": dose, "time_of_day_label": label,
                    "as_needed": False} for i, name, dose, label, n in meds]
    medications.append({"occurrence_id": f"med_senna#{day}#1", "name": "Senna", "dose": "2 tablets",
                        "time_of_day_label": "bedtime", "as_needed": True})
    tasks = [{"occurrence_id": f"task_knee#{day}#{n}", "description": "Knee exercises", "time_of_day_label": label}
             for n, label in enumerate(("morning", "afternoon", "evening"), 1)]
    tasks += [{"occurrence_id": f"task_walk#{day}#1", "description": "Walking", "clock_time": "07:30"},
              {"occurrence_id": f"task_walk#{day}#2", "description": "Walking", "clock_time": "15:55"},
              {"occurrence_id": f"task_ice#{day}#1", "description": "Ice pack"},
              {"occurrence_id": f"task_rest#{day}#1", "description": "Rest with your leg raised"}]
    return medications, tasks


def _stored(day):
    """The events as append_event would store them."""
    return [{"patient_id": PATIENT, "timestamp": f"event#{key}", "recorded_at": NOW.isoformat(),
             "event_type": kind, "details": details, "idempotency_key": key}
            for kind, details, key in demo_history.build_demo_day(day, "2026-10-23", *_occurrences(day))]


@pytest.fixture
def events():
    return _stored("2026-10-21") + _stored("2026-10-22")


def test_seeded_days_show_morning_medicines_taken_and_tasks_done(events):
    summary = week.calculate_week(events, PATIENT, "Europe/London", NOW)
    days = {d["date"]: d for d in summary["days"]}
    assert days["2026-10-21"]["status"] == days["2026-10-22"]["status"] == "completed"
    assert days["2026-10-21"]["scheduled_doses"] == 2  # Paracetamol and Apixaban mornings
    # Other days are untouched: no history, and today is only what is really recorded.
    assert all(days[d]["status"] == "unknown" for d in ("2026-10-17", "2026-10-20", "2026-10-23"))
    # Margaret is not a test identity, so no synthetic label is shown.
    assert summary["synthetic_demo_history"] is False
    activity = {a["date"]: a["completed_tasks"] for a in week.task_activity(events, PATIENT, summary["days"])}
    assert activity == {"2026-10-17": 0, "2026-10-18": 0, "2026-10-19": 0, "2026-10-20": 0,
                        "2026-10-21": 6, "2026-10-22": 6, "2026-10-23": 0}


def test_day_details_list_every_scheduled_dose_and_task(events):
    details = recovery_day.build_day_details({"timezone": "Europe/London"}, events, PATIENT, "2026-10-21", NOW)
    assert details["schedule_evidence"] == "snapshot" and details["scope"] == "all_scheduled"
    assert [m["status"] for m in details["medications"]] == ["taken"] * 6
    assert "Senna" not in [m["name"] for m in details["medications"]]  # as needed: never scheduled
    assert [t["status"] for t in details["tasks"]] == ["completed"] * 6 + ["unknown"]
    assert details["tasks"][4]["recorded_at"] == "2026-10-21T16:05:00+01:00"  # 15:55 walk + 10 minutes
    assert details["synthetic_demo_history"] is False


def test_keys_are_marked_for_removal_and_today_is_refused():
    built = demo_history.build_demo_day("2026-10-21", "2026-10-23", *_occurrences("2026-10-21"))
    assert all(key.startswith(demo_history.KEY_PREFIX + PATIENT) for _, _, key in built)
    assert len({key for _, _, key in built}) == len(built)
    assert all(details["plan_version"] == demo_history.PLAN_VERSION for _, details, _ in built)
    for day in ("2026-10-23", "2026-10-24"):
        with pytest.raises(ValueError):
            demo_history.build_demo_day(day, "2026-10-23", *_occurrences(day))


def test_today_lists_all_of_todays_tasks_not_only_the_recorded_ones(events):
    _, tasks = _occurrences("2026-10-23")
    walk = {"patient_id": PATIENT, "timestamp": "event#walk", "event_type": "task_completed", "idempotency_key": "walk",
            "details": {"date": "2026-10-23", "occurrence_id": "task_walk#2026-10-23#1", "completed_at": "2026-10-23T07:40:00+01:00"}}
    state = {"timezone": "Europe/London", "current_medications": [], "current_tasks": tasks}
    today = recovery_day.build_day_details(state, events + [walk], PATIENT, "2026-10-23", NOW)
    assert len(today["tasks"]) == 7
    assert [t["status"] for t in today["tasks"]].count("completed") == 1
    # Today's plan is never projected backwards: a past day keeps its own saved schedule only.
    past = recovery_day.build_day_details(state, events, PATIENT, "2026-10-20", NOW)
    assert past["tasks"] == []
