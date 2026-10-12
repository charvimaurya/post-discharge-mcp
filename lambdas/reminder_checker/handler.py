"""AWS Lambda entry point for proactive recovery reminders."""

from app.clock import allows_test_hooks, get_patient_datetime, parse_demo_now, system_now_utc

from app.database.recovery_state import (
    clear_pending_checkin,
    get_medications,
    get_recovery_state,
    get_today_tasks,
    save_pending_checkin,
)

from app.reminders import config
from app.reminders.engine import choose_checkin
from app.observability.log import get_request_id, reset_request_id, service_log, set_request_id


log = service_log("reminder_lambda")


DEMO_PATIENT_ID = "demo_patient_001"


def _first_name(state: dict) -> str | None:
    """
    Resolve the patient's first name from RecoveryState, or None.

    With no name the reminder says "Good morning." rather than
    "Good morning, there."
    """
    if state.get("first_name"):
        return state["first_name"]

    if state.get("patient_name"):
        return str(state["patient_name"]).split()[0]

    return None


def handler(event, context):
    """Run one check and log one line: checkin_created, or checkin_skipped with the reason."""

    # A scheduled run has no caller id; a run from the bridge keeps the request's id.
    token = set_request_id(get_request_id() or getattr(context, "aws_request_id", None))

    try:
        result = _check(event)

        if result.get("created"):
            checkin_type = result["pending_checkin"].get("type")
            log("checkin_created", checkin_type=checkin_type)
        else:
            reason = result.get("reason")
            log("checkin_skipped", reason=reason)

        return result

    except Exception as exc:
        log("checkin_failed", level="error", error=exc)
        raise

    finally:
        reset_request_id(token)


def _check(event) -> dict:
    if event.get("force_next") and not allows_test_hooks():
        return {"created": False, "reason": "force_next_disabled"}

    # Manual test runs may pass demo_now; scheduled runs never do,
    # so they always use the real shared clock.
    demo_now = None

    if event.get("demo_now"):
        try:
            demo_now = parse_demo_now(str(event["demo_now"]))
        except ValueError as exc:
            return {
                "created": False,
                "reason": "invalid_demo_now",
                "error": str(exc),
            }

    patient_id = event.get(
        "patient_id",
        DEMO_PATIENT_ID,
    )

    state = get_recovery_state(patient_id)

    if not state:
        return {
            "created": False,
            "reason": "patient_not_found",
        }

    # Plan clock times are local, so "now" and "today" must be too.
    now = get_patient_datetime(
        state.get("timezone") or "Europe/London",
        now=demo_now,
    )

    today = now.date().isoformat()

    tasks = get_today_tasks(
        patient_id,
        today,
    )

    medications = get_medications(
        patient_id,
        today,
    )

    first_name = _first_name(state)
    forced = bool(event.get("force_next"))

    # The engine applies the shared rules and picks one check-in.
    decision = choose_checkin(
        state,
        tasks,
        medications,
        now,
        real_now_utc=system_now_utc(),
        first_name=first_name,
        force_next=forced,
    )

    if decision.expired:
        # Its item is done or its window is over: it is cleared, answered or not.
        clear_pending_checkin(patient_id)

    if decision.reason == "checkin_waiting":
        # Sticky: the waiting check-in is returned unchanged, never replaced.
        return {
            "created": False,
            "reason": "checkin_waiting",
            "pending_checkin": state["pending_checkin"],
        }

    if decision.checkin is None:
        return {
            "created": False,
            "reason": decision.reason,
        }

    checkin = decision.checkin
    pending_checkin = checkin.as_pending(today, now)

    if forced:
        # Test hook: only the usual "never the same key twice" rule.
        created = save_pending_checkin(patient_id, pending_checkin, checkin.checkin_id)
    else:
        remaining = None
        if checkin.scheduled_id:
            remaining = [
                entry for entry in state.get("scheduled_checkins") or []
                if entry.get("checkin_id") != checkin.scheduled_id
            ]
        created = save_pending_checkin(
            patient_id,
            pending_checkin,
            checkin.checkin_id,
            today=today,
            max_per_day=config.max_checkins_per_day(),
            scheduled_checkins=remaining,
        )

    if not created:
        return {
            "created": False,
            "reason": "already_reminded",
            "checkin_id": checkin.checkin_id,
        }

    return {
        "created": True,
        "pending_checkin": pending_checkin,
    }
