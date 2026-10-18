"""Read-only day details. Historical schedules come only from saved snapshots."""
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from app.clock import get_patient_datetime
from app.database.event_history import get_complete_patient_events
from app.database.recovery_state import get_recovery_state, get_medications
from app.mcp.results import success_result, error_result
from app.mcp.tools.week import aware, SYNTHETIC_PATIENTS

PERIODS = {"morning", "midday", "afternoon", "evening", "night", "bedtime"}


def recorded(event):
    details = event.get("details") or {}
    stamp = details.get("completed_at") or event.get("recorded_at")
    return stamp if aware(stamp) else None


def action_status(events, occurrence, kind, now, due=None, version=None):
    rows = {}
    invalid = False
    for event in events:
        details = event.get("details") or {}
        if details.get("occurrence_id") != occurrence or event.get("event_type") not in {
                f"{kind}_taken" if kind == "medication" else "task_completed", f"{kind}_undone", f"{kind}_missed"}:
            continue
        key = event.get("idempotency_key")
        if not key or (version is not None and details.get("plan_version") != version):
            invalid = True
            continue
        if key in rows and rows[key] != event:
            invalid = True
        rows[key] = event
    positive = [e for e in rows.values() if e["event_type"] in {"medication_taken", "task_completed"}]
    undone = sum(e["event_type"].endswith("_undone") for e in rows.values())
    missed = [e for e in rows.values() if e["event_type"].endswith("_missed")]
    if invalid or undone > len(positive) or len(positive) - undone > 1 or (missed and len(positive) > undone):
        return "unknown", None
    if len(positive) > undone:
        stamps = [recorded(e) for e in positive]
        if not all(stamps):
            return "unknown", None
        return "taken" if kind == "medication" else "completed", max(stamps, key=lambda s: aware(s))
    if missed:
        stamps = [recorded(e) for e in missed]
        return ("missed", max(stamps, key=lambda s: aware(s))) if all(stamps) else ("unknown", None)
    return ("not_yet_due", None) if due and due > now else ("unknown", None)


def historical_schedule(events, kind, day, timezone):
    snapshots = [e["details"] for e in events if e.get("event_type") == kind]
    if not snapshots:
        return None
    first = snapshots[0]
    if (any(s != first for s in snapshots[1:]) or first.get("complete") is not True
            or first.get("timezone") != timezone or not isinstance(first.get("plan_version"), str)
            or not first["plan_version"]
            or not isinstance(first.get("occurrences"), list)):
        return None
    ids = set()
    for item in first["occurrences"]:
        if not isinstance(item, dict):
            return None
        if item.get("active") is False or item.get("as_needed") is True:
            continue
        key, due = item.get("occurrence_id"), aware(item.get("due_at"))
        if (item.get("active") is not True or not isinstance(key, str) or key in ids
                or key.rsplit("#", 2)[-2:-1] != [day] or due is None
                or due.astimezone(ZoneInfo(timezone)).date().isoformat() != day):
            return None
        ids.add(key)
    return first


def build_day_details(state, events, patient_id, day, now):
    if now.utcoffset() is None:
        raise ValueError("Aware clock required")
    timezone = state.get("timezone") or "Europe/London"
    local = now.astimezone(ZoneInfo(timezone))
    selected = date.fromisoformat(day)
    if selected.isoformat() != day or not local.date() - timedelta(days=6) <= selected <= local.date():
        raise ValueError("Date outside seven-day window")
    rows = [e for e in events if isinstance(e, dict) and e.get("patient_id") == patient_id
            and isinstance(e.get("details"), dict) and e["details"].get("date") == day]
    full_present = any(e.get("event_type") == "medication_schedule_snapshot" for e in rows)
    snapshot = historical_schedule(rows, "medication_schedule_snapshot" if full_present else "morning_schedule_snapshot", day, timezone)
    current = selected == local.date() and not any(e.get("event_type") in {
        "medication_schedule_snapshot", "morning_schedule_snapshot"} for e in rows)
    medications = []
    if current:
        # Only today's current schedule is authoritative; never project it backwards.
        for item in state.get("current_medications", []):
            if item.get("as_needed"):
                continue
            key = item.get("occurrence_id")
            if not isinstance(key, str) or key.rsplit("#", 2)[-2:-1] != [day]:
                continue
            status, stamp = action_status(rows, key, "medication", local)
            # Preserve ambiguity and explicit misses; do not use cached plan status.
            medications.append({"occurrence_id": key, "name": item.get("name"),
                "dose": item.get("dose"), "period": item.get("time_of_day_label"),
                "due_at": None, "status": status, "recorded_at": stamp,
                "needs_confirmation": item.get("needs_confirmation") is True})
    elif snapshot:
        for item in snapshot["occurrences"]:
            if item.get("active") is False or item.get("as_needed") is True:
                continue
            period = item.get("period")
            status, stamp = action_status(rows, item["occurrence_id"], "medication", local,
                                          aware(item["due_at"]), snapshot["plan_version"])
            if period not in PERIODS:
                status, stamp = "unknown", None
            medications.append({"occurrence_id": item["occurrence_id"], "name": item.get("name"),
                "dose": item.get("dose"), "period": period, "due_at": item["due_at"],
                "status": status, "recorded_at": stamp,
                "needs_confirmation": item.get("needs_confirmation") is True})
    tasks = []
    task_snapshot = historical_schedule(rows, "task_schedule_snapshot", day, timezone)
    task_items = task_snapshot["occurrences"] if task_snapshot else []
    # Saved task actions can be shown even without a historical task denominator.
    known = {item["occurrence_id"] for item in task_items}
    for event in rows:
        details = event["details"]
        key = details.get("occurrence_id")
        if (event.get("event_type") == "task_completed" and isinstance(key, str)
                and key.rsplit("#", 2)[-2:-1] == [day] and key not in known):
            task_items = [*task_items, {"occurrence_id": key, "name": details.get("task_description") or details.get("description")}]
            known.add(key)
    for item in task_items:
        if item.get("active") is False:
            continue
        status, stamp = action_status(rows, item["occurrence_id"], "task", local)
        tasks.append({"occurrence_id": item["occurrence_id"], "name": item.get("name"),
                      "status": status, "recorded_at": stamp})
    return {"kind": "recovery_day_details", "schema_version": 1, "date": day, "timezone": timezone,
        "as_of": now.isoformat(), "schedule_evidence": "current_day_occurrences" if current else "snapshot" if snapshot else "missing_or_conflicting",
        "scope": "all_scheduled" if current or full_present else "morning_only",
        "synthetic_demo_history": patient_id in SYNTHETIC_PATIENTS and bool(rows) and all(e.get("synthetic") is True for e in rows),
        "medications": medications, "tasks": tasks}


def get_recovery_day_details_for_context(context, day):
    try:
        state = get_recovery_state(context.patient_id)
        if not state:
            raise ValueError("No plan")
        state = dict(state)
        now = get_patient_datetime(state.get("timezone") or "Europe/London")
        if day == now.date().isoformat():
            state["current_medications"] = get_medications(context.patient_id, day)
        result = build_day_details(state, get_complete_patient_events(context.patient_id), context.patient_id, day, now)
        return success_result(data=result, message="Recovery history checked from saved records.")
    except (ValueError, TypeError):
        return error_result(code="DAY_UNAVAILABLE", message="That recovery day could not be checked.", next_step="Choose a date in the displayed week.")
