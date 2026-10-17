"""Deterministic synthetic history for memory-backed tests only. No AWS imports."""
from datetime import datetime, time, timedelta
import hashlib
from zoneinfo import ZoneInfo


PATIENTS = {"isolated_mcpjam_s4", "isolated_week_demo"}


def seed_week_events(patient_id, now, timezone="Europe/London"):
    if patient_id not in PATIENTS or now.utcoffset() is None:
        raise ValueError("Only isolated synthetic patients and aware clocks are allowed")
    zone = ZoneInfo(timezone)
    today = now.astimezone(zone).date()
    rows = []

    def add(kind, details, suffix):
        key = f"synthetic-week#{patient_id}#{details['date']}#{suffix}#{kind}"
        rows.append({"patient_id": patient_id, "timestamp": "event#" + hashlib.sha256(key.encode()).hexdigest(),
                     "recorded_at": now.isoformat(), "event_type": kind, "details": details,
                     "idempotency_key": key, "synthetic": True})

    for offset in range(6, -1, -1):
        day = today - timedelta(days=offset)
        date = day.isoformat()
        common = {"date": date, "plan_version": "synthetic-week-v1"}
        occurrences = [{"occurrence_id": f"{med}#{date}#1", "period": "morning", "active": True,
                        "due_at": datetime.combine(day, time(9), zone).isoformat()} for med in ("dose_a", "dose_b")]
        add("morning_schedule_snapshot", {**common, "complete": True, "timezone": timezone,
                                          "occurrences": occurrences}, "schedule")
        if offset:
            for occurrence in occurrences:
                kind = "medication_missed" if offset == 1 else "medication_taken"
                add(kind, {**common, "occurrence_id": occurrence["occurrence_id"],
                           "completed_at": occurrence["due_at"]} if kind == "medication_taken" else
                    {**common, "occurrence_id": occurrence["occurrence_id"]}, occurrence["occurrence_id"])
    return rows
