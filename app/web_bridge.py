"""
Local HTTP bridge between the Next.js server and the Python app.

Only the Next.js server calls this; the browser never does. The
patient comes from the server-side demo context, and nothing the
caller sends can choose the patient, date or time.
"""

import asyncio
import os
import re
import uuid
from contextlib import asynccontextmanager, suppress

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from app.agent.evidence import related_appointment_lines
from app.agent.service import chat, get_structured_tool_result
from app.agent.next_up import build_opening_message, timing
from app.clock import allows_test_hooks, demo_now_text, get_clock_label, get_patient_datetime, system_now_utc
from app.database.event_history import delete_events
from app.database.recovery_state import (
    add_scheduled_checkin,
    clear_pending_checkin,
    get_recovery_state,
    plan_end_date,
    record_chat_activity,
)
from app.ingestion.document_validation import (
    WRONG_DOCUMENT_MESSAGE, WrongDocumentError, validate_discharge_document,
)
from app.ingestion.pdf_processor import extract_text as extract_pdf_text
from app.mcp.client import call_mcp_tool
from app.mcp.context import get_demo_patient_context
from app.observability.log import (
    Timer, get_request_id, reset_request_id, service_log, set_request_id,
)
from lambdas.reminder_checker.handler import handler as reminder_handler


log = service_log("bridge")

TODAY_ERROR = "Could not load today's plan. Please try again."
CHAT_ERROR = "Sorry, I couldn't reach the assistant. Please try again."


# A question about how long a medicine goes on for: "how long", "when do I stop", "end date".
_ASKS_HOW_LONG = re.compile(
    r"\b(how long|end date|until when|stop taking|when (do|can|should|will) i stop|how many (days|weeks|months))\b",
    re.IGNORECASE,
)

NO_END_DATE_FLAG = "Needs confirmation: the letter gives no end date"
NO_END_DATE_TEXT = "Today's doses stay in the plan. Only the end date is unanswered."


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


async def chat_message(request: Request) -> JSONResponse:
    """
    Run one agent turn for the server-side patient.

    A reminder waiting when the message arrived is cleared only
    after the turn finishes; replying never marks anything done.
    """

    try:
        body = await request.json()
    except ValueError:
        body = None

    message = body.get("message") if isinstance(body, dict) else None

    if not isinstance(message, str) or not message.strip():
        return JSONResponse({"error": "Send a message."}, status_code=400)

    session_id = body.get("session_id")

    if not isinstance(session_id, str) or not session_id.strip():
        session_id = uuid.uuid4().hex

    patient = get_demo_patient_context()

    # When she last spoke (real time), so no check-in interrupts a chat.
    try:
        await asyncio.to_thread(
            record_chat_activity, patient.patient_id, system_now_utc().isoformat()
        )
    except Exception as exc:
        log("chat_activity_failed", level="error", error=exc)

    def schedule(entry: dict) -> None:
        add_scheduled_checkin(patient.patient_id, entry)

    try:
        state = await asyncio.to_thread(
            get_recovery_state, patient.patient_id
        )
        state = state or {}
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
        log("chat_failed", level="error", error=exc, route="/chat")
        return JSONResponse({"error": CHAT_ERROR}, status_code=502)

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
        source = dict(source, related=related)

    note = open_ended_medicine_note(source, f"{message} {result['response']}", state)

    if note:
        source = dict(source, note=note)

    return JSONResponse(
        {
            "response": result["response"],
            "tool_trace": result["tool_trace"],
            "source": source,
            # Only on a symptom reply: who to call, from her letter.
            "help": result.get("help"),
            "session_id": session_id,
            # Shown small in Developer view, to find this turn in the logs.
            "request_id": get_request_id(),
        },
        headers={"Cache-Control": "no-store"},
    )


async def today(request: Request) -> JSONResponse:
    """Today's clock label, task and medicine occurrences, and waiting reminder."""

    patient = get_demo_patient_context()

    try:
        # Tasks and medicines come from the MCP tools, which own the plan rules.
        tasks_result = get_structured_tool_result(
            await call_mcp_tool("get_today_tasks", {})
        )
        medications_result = get_structured_tool_result(
            await call_mcp_tool("get_medications", {})
        )
        state = await asyncio.to_thread(
            get_recovery_state, patient.patient_id
        )
    except Exception as exc:
        log("today_failed", level="error", error=exc, route="/today")
        return JSONResponse({"error": TODAY_ERROR}, status_code=502)

    for result in (tasks_result, medications_result):
        if not isinstance(result, dict) or not result.get("ok"):
            return JSONResponse({"error": TODAY_ERROR}, status_code=502)

    state = state or {}
    zone = state.get("timezone") or "Europe/London"
    now = get_patient_datetime(zone)

    # Each item says where it sits in the day ("earlier today", "due now",
    # "later", "any time"), from the same clock as everything else.
    tasks = [dict(t, timing=timing(t, now)) for t in tasks_result["data"]["tasks"]]
    medications = [
        dict(m, timing=timing(m, now)) for m in medications_result["data"]["medications"]
    ]

    return JSONResponse(
        {
            "clock_label": get_clock_label(zone, now),
            "opening_greeting": build_opening_message(
                state.get("first_name") or str(state.get("patient_name") or "").split(" ")[0] or None,
                tasks,
                medications,
                now,
            ),
            "date": tasks_result["data"]["date"],
            "discharge_date": state.get("discharge_date"),
            "tasks": tasks,
            "medications": medications,
            "pending_checkin": state.get("pending_checkin"),
        },
        headers={"Cache-Control": "no-store"},
    )


async def validate_document(request: Request) -> JSONResponse:
    """Read the PDF before the upload route sends it to S3 or changes a plan."""
    data = await request.body()
    if not data or b"%PDF-" not in data[:1024]:
        return JSONResponse({"error": WRONG_DOCUMENT_MESSAGE}, status_code=422)
    try:
        pages = await asyncio.to_thread(extract_pdf_text, data)
        text = "\n".join(page.get("text") or "" for page in pages)
        validate_discharge_document(text)
    except WrongDocumentError:
        return JSONResponse({"error": WRONG_DOCUMENT_MESSAGE}, status_code=422)
    except Exception as exc:
        log("document_validation_failed", level="error", error=exc, route="/documents/validate")
        return JSONResponse(
            {"error": "Document not accepted. Please upload a readable, unencrypted PDF discharge letter."},
            status_code=422,
        )
    return JSONResponse({"accepted": True}, headers={"Cache-Control": "no-store"})


HISTORY_ERROR = "Could not clear the previous plan's history."


async def document_uploaded(request: Request) -> JSONResponse:
    """
    A new discharge letter is in S3: delete what was recorded against the old one.

    The upload route calls this after the letter is accepted and stored. The
    new letter replaces the plan, so completions saved for the previous plan
    must not show as done on the new one. The request body is ignored, so the
    caller cannot choose the patient.
    """

    patient = get_demo_patient_context()

    try:
        deleted = await asyncio.to_thread(delete_events, patient.patient_id)
    except Exception as exc:
        log("history_clear_failed", level="error", error=exc, route="/documents/uploaded")
        return JSONResponse({"error": HISTORY_ERROR}, status_code=502)

    log("history_cleared", item_count=deleted)

    return JSONResponse({"deleted": deleted}, headers={"Cache-Control": "no-store"})


# Local stand-in for the EventBridge schedule: with LOCAL_REMINDER_LOOP=1
# the bridge runs the same reminder handler every few seconds, so a demo
# reminder appears without invoking anything by hand.
REMINDER_LOOP_DEFAULT_SECONDS = 15.0


def _reminder_loop_seconds() -> float:
    try:
        seconds = float(os.getenv("REMINDER_LOOP_SECONDS", ""))
    except ValueError:
        return REMINDER_LOOP_DEFAULT_SECONDS

    return seconds if seconds > 0 else REMINDER_LOOP_DEFAULT_SECONDS


def _reminder_event() -> dict:
    # On the real clock the handler reads the time itself, like the
    # scheduled Lambda. On the demo clock the fixed time is passed in.
    demo_now = demo_now_text()

    return {"demo_now": demo_now} if demo_now else {}


REMINDER_CHECK_ERROR = "Could not check for a reminder. Please try again."


async def check_reminder(request: Request) -> JSONResponse:
    """
    Run the reminder handler once, for the demo patient.

    On AWS the EventBridge schedule starts this check. Locally the
    /demo page asks for the same check when the Today screen opens.
    Same handler, same rules. The request body is ignored, so the
    caller cannot choose the patient, date or time.
    """

    event = _reminder_event()

    # Test only: ?force_next=true makes the reminder for the next item
    # now, outside the usual window. Never available in production.
    if request.query_params.get("force_next", "").lower() == "true":
        if not allows_test_hooks():
            return JSONResponse(
                {"error": "force_next is not available in production."}, status_code=403
            )
        event["force_next"] = True

    try:
        result = await asyncio.to_thread(reminder_handler, event, None)
    except Exception as exc:
        log("reminder_check_failed", level="error", error=exc, route="/reminders/check")
        return JSONResponse({"error": REMINDER_CHECK_ERROR}, status_code=502)

    return JSONResponse(result, headers={"Cache-Control": "no-store"})


def run_reminder_once() -> str:
    """Call the reminder handler once and log the outcome in one line."""

    try:
        result = reminder_handler(_reminder_event(), None)
    except Exception as exc:
        log("local_reminder_check", level="warning", error=exc, status="error")
        return "error"

    outcome = "created" if result.get("created") else str(result.get("reason") or "unknown")
    log("local_reminder_check", status=outcome)

    return outcome


async def reminder_loop(interval: float) -> None:
    while True:
        # The handler uses boto3, which blocks, so keep it off the event loop.
        await asyncio.to_thread(run_reminder_once)
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app: Starlette):
    task = None

    if os.getenv("LOCAL_REMINDER_LOOP") == "1":
        interval = _reminder_loop_seconds()
        log("local_reminder_loop_on", ms=int(interval * 1000))
        task = asyncio.create_task(reminder_loop(interval))

    app.state.reminder_task = task

    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


class RequestLogMiddleware:
    """
    One request id per request, and a request_start / request_end line.

    The id comes from X-Request-ID (set by the Next.js route) or is made
    here. It is kept in a contextvar, so the agent's lines and the MCP
    calls made for this request carry the same id, and it is sent back
    in the response header.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {key.decode("latin-1").lower(): value.decode("latin-1") for key, value in scope.get("headers", [])}
        token = set_request_id(headers.get("x-request-id"))
        route = scope.get("path", "")
        timer = Timer()
        status = 500

        async def send_with_id(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message = dict(message, headers=[
                    *message.get("headers", []), (b"x-request-id", get_request_id().encode("latin-1")),
                ])
            await send(message)

        log("request_start", route=route)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            log("request_end", route=route, status=status, ms=timer.ms)
            reset_request_id(token)


app = Starlette(
    routes=[
        Route("/documents/validate", validate_document, methods=["POST"]),
        Route("/documents/uploaded", document_uploaded, methods=["POST"]),
        Route("/chat", chat_message, methods=["POST"]),
        Route("/today", today, methods=["GET"]),
        Route("/reminders/check", check_reminder, methods=["POST"]),
    ],
    lifespan=lifespan,
    middleware=[Middleware(RequestLogMiddleware)],
)
