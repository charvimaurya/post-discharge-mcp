"""Evidence-based weekly adherence. Silence and current plans are not history."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.clock import get_patient_datetime
from app.demo_history import ensure_demo_history
from app.database.event_history import get_complete_patient_events
from app.database.recovery_state import _completed, _completion_rounds, get_medications, get_recovery_state
from app.mcp.results import error_result, success_result
from app.mcp.tools.recovery import get_today_tasks_for_context

# Test identities only. A name or client-provided flag cannot establish provenance.
SYNTHETIC_PATIENTS = frozenset({"isolated_mcpjam_s4", "isolated_week_demo"})
ACTION_TYPES = {"medication_taken", "medication_undone", "medication_missed"}


def aware(value):
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return stamp if stamp.utcoffset() is not None else None
    except (ValueError, TypeError, AttributeError):
        return None


def schedule(details, day, timezone):
    """Validate a complete historical snapshot; never expand today's plan backward."""
    if (details.get("complete") is not True or details.get("timezone") != timezone
            or not isinstance(details.get("plan_version"), str) or not details["plan_version"]
            or not isinstance(details.get("occurrences"), list)):
        return None
    expected = {}
    for item in details["occurrences"]:
        if not isinstance(item, dict):
            return None
        # Explicit inactive evidence excludes a stopped/ended dose for this date.
        if item.get("active") is False or item.get("as_needed") is True:
            continue
        occurrence = item.get("occurrence_id")
        due = aware(item.get("due_at"))
        if (item.get("active") is not True or item.get("period") != "morning"
                or not isinstance(occurrence, str) or occurrence.rsplit("#", 2)[-2:-1] != [day]
                or occurrence in expected or due is None
                or due.astimezone(ZoneInfo(timezone)).date().isoformat() != day):
            return None
        expected[occurrence] = due
    return expected


def calculate_week(events, patient_id, timezone, now):
    if now.utcoffset() is None:
        raise ValueError("An aware application time is required")
    zone = ZoneInfo(timezone)
    local_now = now.astimezone(zone)
    today = local_now.date()
    days = []
    relevant = []
    for offset in range(6, -1, -1):
        date = today - timedelta(days=offset)
        day = date.isoformat()
        rows = [e for e in events if isinstance(e, dict) and e.get("patient_id") == patient_id
                and isinstance(e.get("details"), dict) and e["details"].get("date") == day
                and e.get("event_type") in ACTION_TYPES | {"morning_schedule_snapshot"}]
        relevant.extend(rows)
        snapshots = [e["details"] for e in rows if e["event_type"] == "morning_schedule_snapshot"]
        result = {"date": day, "is_today": date == today, "status": "unknown",
                  "reason": "missing_schedule_evidence", "scheduled_doses": None,
                  "taken_doses": None, "explicitly_missed_doses": None, "schedule_evidence": "missing"}
        days.append(result)
        if not snapshots:
            continue
        result["schedule_evidence"] = "snapshot"
        expected = schedule(snapshots[0], day, timezone)
        if expected is None or any(s != snapshots[0] for s in snapshots[1:]):
            result["reason"] = "incomplete_or_conflicting_schedule"
            continue
        version = snapshots[0]["plan_version"]
        taken = set()
        missed = set()
        ambiguous = False
        for occurrence in expected:
            # Retry events have identical deterministic keys; never double-count them.
            actions = {}
            for event in rows:
                details = event["details"]
                if event["event_type"] not in ACTION_TYPES or details.get("occurrence_id") != occurrence:
                    continue
                key = event.get("idempotency_key")
                if not isinstance(key, str) or not key or details.get("plan_version") != version:
                    ambiguous = True
                    continue
                if event["event_type"] in {"medication_taken", "medication_missed"} and aware(
                        details.get("completed_at") or event.get("recorded_at")) is None:
                    ambiguous = True
                    continue
                if key in actions and actions[key] != event:
                    ambiguous = True
                actions[key] = event
            positive = sum(e["event_type"] == "medication_taken" for e in actions.values())
            undone = sum(e["event_type"] == "medication_undone" for e in actions.values())
            negative = any(e["event_type"] == "medication_missed" for e in actions.values())
            if undone > positive or positive - undone > 1:
                ambiguous = True
            if positive > undone:
                taken.add(occurrence)
            if negative:
                missed.add(occurrence)
        result.update(scheduled_doses=len(expected), taken_doses=len(taken), explicitly_missed_doses=len(missed))
        if ambiguous or taken & missed:
            result["reason"] = "conflicting_or_unversioned_actions"
        elif not expected:
            result.update(status="no_scheduled_morning_doses", reason="empty_evidenced_schedule")
        elif len(taken) == len(expected):
            result.update(status="completed", reason="all_scheduled_morning_doses_recorded")
        elif missed:
            result.update(status="missed", reason="explicit_missed_record")
        elif any(due > local_now for occurrence, due in expected.items() if occurrence not in taken):
            result.update(status="not_yet_due", reason="outstanding_dose_not_yet_due")
        else:
            result["reason"] = "partial_completion" if taken else "no_completion_evidence"
    return {"start_date": days[0]["date"], "end_date": days[-1]["date"],
            "completed_days": sum(d["status"] == "completed" for d in days), "total_days": 7,
            "synthetic_demo_history": patient_id in SYNTHETIC_PATIENTS and bool(relevant)
            and all(e.get("synthetic") is True for e in relevant), "days": days}


def apply_current_morning(week, medications):
    """Use the authoritative occurrence reader for today, never for past dates.

    That reader excludes withdrawn/ended doses and rebuilds completion, including
    undo, from saved events. A current plan is not evidence of a past schedule.
    """
    day = week["days"][-1]
    # Preserve explicit historical evidence, including conflicts, when present.
    if day["reason"] != "missing_schedule_evidence":
        return
    scheduled = [item for item in medications if not item.get("as_needed")]
    labels = [str(item.get("time_of_day_label") or "").strip().lower() for item in scheduled]
    if any(label not in {"morning", "midday", "afternoon", "evening", "night", "bedtime"}
           for label in labels):
        day["reason"] = "incomplete_current_schedule"
        return
    morning = [item for item, label in zip(scheduled, labels) if label == "morning"]
    # Reject malformed, duplicate or cross-date occurrences rather than guessing.
    ids = [item.get("occurrence_id") for item in morning]
    if (any(not isinstance(key, str) or key.rsplit("#", 2)[-2:-1] != [day["date"]] for key in ids)
            or len(set(ids)) != len(ids)):
        day["reason"] = "incomplete_current_schedule"
        return
    taken = sum(item.get("status") == "completed" and aware(item.get("completed_at")) is not None for item in morning)
    day.update(schedule_evidence="current_day_occurrences", scheduled_doses=len(morning),
               taken_doses=taken, explicitly_missed_doses=0)
    if not morning:
        day.update(status="no_scheduled_morning_doses", reason="empty_current_schedule")
    elif taken == len(morning):
        day.update(status="completed", reason="all_current_morning_doses_recorded")
    else:
        day.update(status="unknown", reason="partial_completion" if taken else "no_completion_evidence")
    week["completed_days"] = sum(item["status"] == "completed" for item in week["days"])
    # A current-day read does not establish synthetic provenance.
    week["synthetic_demo_history"] = False


def task_activity(events, patient_id, days):
    """Counts of distinct saved task occurrences, not historical adherence rates.

    Use the same completion/undo rules as Today, scoped to the occurrence date.
    Repeated delivery of a stored idempotency key must not inflate the series.
    """
    unique = {}
    for event in events:
        if event.get("patient_id") != patient_id or event.get("event_type") not in {"task_completed", "task_undone"}:
            continue
        key = event.get("idempotency_key") or event.get("timestamp")
        details = event.get("details") or {}
        occurrence = details.get("occurrence_id")
        if (not key or not isinstance(occurrence, str)
                or occurrence.rsplit("#", 2)[-2:-1] != [details.get("date")]):
            continue
        unique.setdefault(key, event)
    return [{"date": day["date"], "completed_tasks": len(_completed(
        _completion_rounds(list(unique.values()), "task", day["date"]))) } for day in days]


def get_week_summary_for_context(context):
    try:
        state = get_recovery_state(context.patient_id)
        if state is None:
            raise ValueError("No plan")
        timezone = state.get("timezone") or "Europe/London"
        now = get_patient_datetime(timezone)
        events = get_complete_patient_events(context.patient_id)
        events = ensure_demo_history(context.patient_id, state, events, now)
        week = calculate_week(events, context.patient_id, timezone, now)
        week["discharge_date"] = state.get("discharge_date")
        week["activity"] = task_activity(events, context.patient_id, week["days"])
        if isinstance(state.get("medications"), list):
            apply_current_morning(week, get_medications(context.patient_id, week["end_date"]))
        today = get_today_tasks_for_context(context)
        if not today.get("ok") or today["data"]["date"] != week["end_date"]:
            raise ValueError("Today snapshot unavailable")
        return success_result(data={"kind": "week_summary", "schema_version": 1,
            "timezone": timezone, "as_of": now.isoformat(), "today": today["data"], "week": week},
            message=f"{week['completed_days']} of 7 days: all morning medicines taken")
    except Exception:
        # Never echo backend diagnostics or record identifiers into the tool result.
        return error_result(code="WEEK_UNAVAILABLE", message="The weekly summary could not be checked.",
                            next_step="Please try again later.")
