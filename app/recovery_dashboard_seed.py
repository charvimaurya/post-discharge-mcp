"""Pure, deterministic synthetic fixture for a dedicated dashboard patient."""
import hashlib

PATIENT = "isolated_week_demo"
VERSION = "recovery-dashboard-2026-10-v1"
NOW = "2026-10-23T07:00:00+01:00"


def build_seed():
    plan = {"patient_id": PATIENT, "first_name": "Synthetic demo", "timezone": "Europe/London",
        "discharge_date": "2026-10-20", "ingestion_status": "ready", "synthetic": True,
        "synthetic_history_version": VERSION,
        "medications": [{"id": "demo_medicine_a", "name": "Synthetic medicine A", "dose": "1 demo tablet",
                         "time_of_day": ["morning"], "times_per_day": 1},
                        {"id": "demo_medicine_b", "name": "Synthetic medicine B", "dose": "1 demo tablet",
                         "time_of_day": ["morning"], "times_per_day": 1}],
        "tasks": [{"id": "demo_walk", "description": "Synthetic morning walk", "times_per_day": 1,
                   "clock_times": ["06:30"]}]}
    events = []

    def add(kind, day, suffix, details, time="06:45"):
        key = f"{VERSION}#{PATIENT}#{day}#{kind}#{suffix}"
        stamp = f"{day}T{time}:00+01:00"
        events.append({"patient_id": PATIENT, "timestamp": "event#" + hashlib.sha256(key.encode()).hexdigest(),
            "idempotency_key": key, "recorded_at": stamp, "synthetic": True, "event_type": kind,
            "details": {"date": day, "plan_version": VERSION, **details}})

    for number in range(20, 24):
        day = f"2026-10-{number}"
        medicines = [{"occurrence_id": f"{m['id']}#{day}#1", "name": m["name"], "dose": m["dose"],
                      "period": "morning", "active": True, "as_needed": False,
                      "due_at": f"{day}T06:30:00+01:00"} for m in plan["medications"]]
        common = {"complete": True, "timezone": "Europe/London", "occurrences": medicines}
        add("morning_schedule_snapshot", day, "morning", common)
        add("medication_schedule_snapshot", day, "all-medicines", common)
        for index, med in enumerate(medicines):
            # 20: complete, 21: explicitly missed, 22: partial/unknown, 23: complete.
            if number == 22 and index == 1:
                continue
            missed = number == 21 and index == 1
            add("medication_missed" if missed else "medication_taken", day, med["occurrence_id"],
                {"occurrence_id": med["occurrence_id"], **({} if missed else {"completed_at": f"{day}T06:45:00+01:00"})})
        task_id = f"demo_walk#{day}#1"
        add("task_schedule_snapshot", day, "tasks", {"complete": True, "timezone": "Europe/London",
            "occurrences": [{"occurrence_id": task_id, "name": "Synthetic morning walk", "active": True,
                             "due_at": f"{day}T06:30:00+01:00"}]})
        add("task_completed", day, "walk", {"occurrence_id": task_id, "task_id": "demo_walk",
            "description": "Synthetic morning walk", "completed_at": f"{day}T06:50:00+01:00"}, "06:50")
    return plan, events
