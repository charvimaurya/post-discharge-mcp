"""
One conversation turn for the server-side demo patient.

Shared by every way she can talk to AfterWard (the web bridge's /chat
route today). The patient comes from the server-side demo context, and
nothing the caller sends can choose the patient, date or time.
"""

import asyncio
import re

from app.agent.evidence import related_appointment_lines
from app.agent.safety import _ASKS_HOW_LONG
from app.agent.service import chat, crisis_reply_without_record
from app.clock import system_now_utc
from app.database.recovery_state import (
    add_scheduled_checkin,
    clear_pending_checkin,
    get_recovery_state,
    plan_end_date,
    record_chat_activity,
)
from app.demo_reset import reset_if_idle
from app.mcp.context import get_demo_patient_context
from app.observability.log import service_log


# Same service name as before the move, so the log lines are unchanged.
log = service_log("bridge")

NO_END_DATE_FLAG = "Needs confirmation: the letter gives no end date"
NO_END_DATE_TEXT = "Today's doses stay in the plan. Only the end date is unanswered."


class TurnFailed(Exception):
    """Reading her record or running the agent failed; the caller answers with its error."""


def open_ended_medicine_note(source: dict | None, conversation: str, state: dict) -> dict | None:
    """
    The note shown under a medicine whose letter line gives no end date.

    Only when the turn is about how long to take it, the marked line is one
    regular medicine in the plan, and neither an end date nor a length
    ("for 14 days") can be read from the letter. Nothing is said about a
    medicine that has an end, or one taken only if needed.
    """

    if not source or not _ASKS_HOW_LONG.search(conversation or ""):
        return None

    marked = str(source.get("highlight") or "").lower()
    medicines = [
        medicine for medicine in state.get("medications") or []
        if isinstance(medicine, dict)
        and str(medicine.get("name") or "").strip()
        and str(medicine["name"]).lower().split()[0] in re.findall(r"[a-z]+", marked)
    ]

    if len(medicines) != 1:
        return None

    (medicine,) = medicines

    if medicine.get("as_needed") or plan_end_date(medicine, state) is not None:
        return None

    return {"flag": NO_END_DATE_FLAG, "text": NO_END_DATE_TEXT}


async def run_turn(message: str, session_id: str) -> dict:
    """
    Run one agent turn for the server-side patient: {"response", "tool_trace", "source", "help", "crisis"}.

    A reminder waiting when the message arrived is cleared only
    after the turn finishes; replying never marks anything done.
    Raises TurnFailed if her record cannot be read or the agent fails.
    """

    patient = get_demo_patient_context()

    def schedule(entry: dict) -> None:
        add_scheduled_checkin(patient.patient_id, entry)

    # The first message after a long gap starts from a fresh day (the demo clock never
    # moves on). Checked before this message counts as activity.
    try:
        if await asyncio.to_thread(reset_if_idle):
            log("demo_idle_reset")
    except Exception as exc:
        log("idle_reset_failed", level="error", error=exc)

    try:
        # Read first; when she last spoke is recorded only after a non-crisis reply.
        state = await asyncio.to_thread(get_recovery_state, patient.patient_id) or {}
    except Exception as exc:
        # Her record is unreadable, but a crisis message still gets its fixed reply:
        # the crisis check needs no record. Anything else fails as before.
        crisis = crisis_reply_without_record(message, session_id)
        if crisis is None:
            raise TurnFailed() from exc
        log("state_read_failed", level="error", error=exc, reason="crisis_answered")
        return {"response": crisis["response"], "tool_trace": [], "source": None, "help": None, "crisis": True}

    try:
        had_checkin = bool(state.get("pending_checkin"))

        # The agent gets the waiting reminder, name and time zone
        # from the server's own record, never from the message.
        result = await chat(
            message,
            session_id,
            pending_checkin=state.get("pending_checkin"),
            first_name=state.get("first_name"),
            timezone=state.get("timezone") or "Europe/London",
            schedule_checkin=schedule,
        )
    except Exception as exc:
        raise TurnFailed() from exc

    if not result.get("crisis"):
        # Real time, so no check-in interrupts a chat. A crisis turn writes no chat metadata.
        try:
            await asyncio.to_thread(record_chat_activity, patient.patient_id, system_now_utc().isoformat())
        except Exception as exc:
            log("chat_activity_failed", level="error", error=exc)

    # A crisis reply is not an answer to the reminder, so the reminder stays.
    if had_checkin and result.get("completed") and not result.get("crisis"):
        try:
            await asyncio.to_thread(
                clear_pending_checkin, patient.patient_id
            )
        except Exception as exc:
            # The reply is already real; the reminder just stays visible.
            log("clear_checkin_failed", level="error", error=exc)

    # A passage that points at an appointment ("until your consultant has reviewed
    # you") is shown with that appointment's own line from the letter, if the plan has it.
    source = result["source"]
    related = related_appointment_lines(source, state.get("appointments"))

    if related:
        # Added to any line the agent already linked (the letter's emergency number).
        source = dict(source, related=[*(source.get("related") or []), *related])

    note = open_ended_medicine_note(source, f"{message} {result['response']}", state)

    if note:
        source = dict(source, note=note)

    return {
        "response": result["response"],
        "tool_trace": result["tool_trace"],
        "source": source,
        # Only on a symptom reply: who to call, from her letter.
        "help": result.get("help"),
        # The fixed crisis reply: nothing may follow it (no "Anything else?").
        "crisis": bool(result.get("crisis")),
    }
