"""
Authenticated HTTP bridge between the Next.js server and the Python app.

Only the Next.js server calls this using X-Bridge-Key; the browser never does. The
patient comes from the server-side demo context, and nothing the
caller sends can choose the patient, date or time.
"""

import asyncio
import os
import uuid
from contextlib import asynccontextmanager, suppress

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from app.auth.bridge_auth import BridgeAuthenticationMiddleware, is_production

from app.agent.session import clear_session
from app.agent.service import get_structured_tool_result
from app.agent.next_up import build_opening_message, timing
from app.clock import allows_test_hooks, demo_now_text, get_clock_label, get_patient_datetime
from app.database.event_history import delete_events
from app.demo_reset import NoPlanToReset, reset_demo_patient, reset_if_idle
from app.rate_limit import RateLimiter
from app.database.recovery_state import (
    clear_pending_checkin,
    get_recovery_state,
    record_greeting,
)
from app.ingestion.document_validation import (
    WRONG_DOCUMENT_MESSAGE, WrongDocumentError, validate_discharge_document,
)
from app.ingestion.pdf_processor import extract_text as extract_pdf_text
from app.mcp.client import call_mcp_tool, mcp_turn
from app.mcp.context import get_demo_patient_context
from app.observability.log import (
    Timer, get_request_id, reset_request_id, service_log, set_request_id,
)
from app.alexa import feed as alexa_feed
from app.alexa.skill import alexa_endpoint
from app.turn import TurnFailed, run_turn
from lambdas.reminder_checker.handler import handler as reminder_handler
from app.reminders.engine import pending_is_valid


log = service_log("bridge")

TODAY_ERROR = "Could not load today's plan. Please try again."
CHAT_ERROR = "Sorry, I couldn't reach the assistant. Please try again."

# Demo chat limits, per bridge process: 30 messages per session and 100 per
# visitor IP address in any hour. Over either, the reply is CHAT_LIMIT_REPLY.
CHAT_LIMIT_REPLY = "You've reached the demo limit for now. Please try again in a little while."
CHAT_SESSION_LIMIT = RateLimiter(limit=30, window_seconds=3600)
CHAT_IP_LIMIT = RateLimiter(limit=100, window_seconds=3600)

# The visitor's address, worked out by the web server from the trusted proxy's
# headers (web/lib/client-ip.ts) and passed on in this header.
CLIENT_IP_HEADER = "x-afterward-client-ip"


def _client_ip(request: Request) -> str:
    """
    The visitor IP address used for the per-IP chat limit.

    X-AfterWard-Client-IP is trusted only because the web server sets it and the
    bridge listens on 127.0.0.1, so nothing else can reach it. When the bridge key
    is added in step 9a, trust this header only on requests that pass the key
    check; otherwise fall back to the peer address.
    """

    forwarded = request.headers.get(CLIENT_IP_HEADER, "").strip()
    if forwarded:
        return forwarded

    return request.client.host if request.client else "unknown"


def _chat_limit_hit(session_id: str, client_ip: str) -> str | None:
    """Which limit this message would break ("session" or "ip"), or None."""

    if not CHAT_SESSION_LIMIT.allowed(session_id):
        return "session"

    if not CHAT_IP_LIMIT.allowed(client_ip):
        return "ip"

    return None


async def chat_message(request: Request) -> JSONResponse:
    """Run one agent turn for the server-side patient (see app.turn.run_turn)."""

    try:
        body = await request.json()
    except ValueError:
        body = None

    message = body.get("message") if isinstance(body, dict) else None

    if isinstance(body, dict) and "patient_id" in body:
        return JSONResponse({"error": "Patient identity is assigned by the server."}, status_code=400)

    if not isinstance(message, str) or not message.strip():
        return JSONResponse({"error": "Send a message."}, status_code=400)

    session_id = body.get("session_id")

    if not isinstance(session_id, str) or not session_id.strip():
        session_id = uuid.uuid4().hex

    # Checked before anything else: over the limit, no DynamoDB write or read,
    # no agent turn and no MCP call.
    client_ip = _client_ip(request)
    limit_hit = _chat_limit_hit(session_id, client_ip)

    if limit_hit:
        log("chat_rate_limited", reason=limit_hit)
        return JSONResponse(
            {
                "response": CHAT_LIMIT_REPLY,
                "tool_trace": [],
                "source": None,
                "help": None,
                "session_id": session_id,
                "request_id": get_request_id(),
                "rate_limited": True,
            },
            headers={"Cache-Control": "no-store"},
        )

    CHAT_SESSION_LIMIT.record(session_id)
    CHAT_IP_LIMIT.record(client_ip)

    try:
        turn = await run_turn(message, session_id)
    except TurnFailed as failed:
        log("chat_failed", level="error", error=failed.__cause__, route="/chat")
        return JSONResponse({"error": CHAT_ERROR}, status_code=502)

    return JSONResponse(
        {
            "response": turn["response"],
            "tool_trace": turn["tool_trace"],
            "source": turn["source"],
            # Only on a symptom reply: who to call, from her letter.
            "help": turn["help"],
            "session_id": session_id,
            # Shown small in Developer view, to find this turn in the logs.
            "request_id": get_request_id(),
        },
        headers={"Cache-Control": "no-store"},
    )


async def idle_reset(route: str) -> bool:
    """reset_if_idle off the event loop. A failure is logged and the visit goes on."""

    try:
        return await asyncio.to_thread(reset_if_idle)
    except Exception as exc:
        log("idle_reset_failed", level="error", error=exc, route=route)
        return False


async def complete_task(request: Request) -> JSONResponse:
    """A selected web task keeps its exact occurrence; MCP validates it for the patient."""
    try:
        body = await request.json()
    except ValueError:
        body = None
    if (not isinstance(body, dict) or set(body) != {"occurrence_id"}
            or not isinstance(body.get("occurrence_id"), str) or not body["occurrence_id"].strip()
            or len(body["occurrence_id"]) > 512):
        return JSONResponse({"error": "Choose one scheduled task."}, status_code=400)
    arguments = {"occurrence_id": body["occurrence_id"].strip()}
    try:
        result = get_structured_tool_result(await call_mcp_tool("report_task_completed", arguments))
        if (not isinstance(result, dict) or result.get("ok") is not True
                or not isinstance(result.get("message"), str)):
            raise ValueError("Task completion was not persisted")
    except Exception as exc:
        log("task_completion_failed", level="error", error=exc, route="/tasks/complete")
        return JSONResponse({"error": "Could not save that task. Please refresh your plan and try again."},
                            status_code=502, headers={"Cache-Control": "no-store"})
    return JSONResponse({"response": result["message"], "source": None, "help": None,
                         "tool_trace": [{"tool": "report_task_completed", "arguments": arguments, "ok": True}]},
                        headers={"Cache-Control": "no-store"})


async def today(request: Request) -> JSONResponse:
    """Today's clock label, task and medicine occurrences, and waiting reminder."""

    if "patient_id" in request.query_params:
        return JSONResponse({"error": "Patient identity is assigned by the server."}, status_code=400)
    patient = get_demo_patient_context()

    # A visit after a long gap starts fresh (the demo clock never moves on).
    if await idle_reset("/today"):
        log("demo_idle_reset", route="/today")

    try:
        # Tasks and medicines come from the MCP tools, which own the plan rules.
        # The two reads and the record read run at once, over one MCP connection.
        async with mcp_turn():
            raw_tasks, raw_medications, state = await asyncio.gather(
                call_mcp_tool("get_today_tasks", {}),
                call_mcp_tool("get_medications", {}),
                asyncio.to_thread(get_recovery_state, patient.patient_id),
            )
        tasks_result = get_structured_tool_result(raw_tasks)
        medications_result = get_structured_tool_result(raw_medications)
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

    first_name = state.get("first_name") or str(state.get("patient_name") or "").split(" ")[0] or None

    # A reminder about something already done is never shown, and is cleared.
    pending = state.get("pending_checkin")
    done = {item.get("occurrence_id") for item in [*tasks, *medications] if item.get("status") == "completed"}

    if pending and pending.get("occurrence_id") in done:
        pending = None
        try:
            await asyncio.to_thread(clear_pending_checkin, patient.patient_id)
        except Exception as exc:
            log("clear_checkin_failed", level="error", error=exc, route="/today")

    return JSONResponse(
        {
            "clock_label": get_clock_label(zone, now),
            # Shown above "Today", so whose plan this is is always on screen.
            "first_name": first_name,
            "opening_greeting": build_opening_message(
                first_name,
                tasks,
                medications,
                now,
                # Already greeted today (the page says so once it has shown a greeting).
                returning=state.get("greeted_on") == now.date().isoformat(),
            ),
            "date": tasks_result["data"]["date"],
            "discharge_date": state.get("discharge_date"),
            "tasks": tasks,
            "medications": medications,
            "pending_checkin": pending if pending and pending_is_valid(pending, tasks, medications, now) else None,
            # Changes on every reset (script, button or idle), so /demo knows to clear its chat.
            "demo_reset_at": state.get("demo_reset_at"),
        },
        headers={"Cache-Control": "no-store"},
    )


async def week_summary(request: Request) -> JSONResponse:
    """Read the authenticated MCP weekly result; no patient/date comes from the caller."""
    if "patient_id" in request.query_params:
        return JSONResponse({"error": "Patient identity is assigned by the server."}, status_code=400)
    try:
        result = get_structured_tool_result(await call_mcp_tool("get_week_summary", {}))
        if not isinstance(result, dict) or not result.get("ok"):
            raise ValueError("Weekly tool unavailable")
        data = result.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("week"), dict):
            raise ValueError("Invalid weekly result")
        return JSONResponse(
            {key: data.get(key) for key in ("week", "timezone", "as_of")},
            headers={"Cache-Control": "no-store"},
        )
    except Exception as exc:
        log("week_summary_failed", level="error", error=exc, route="/week-summary")
        return JSONResponse({"error": "The weekly summary could not be checked."}, status_code=502)


async def recovery_day(request: Request) -> JSONResponse:
    params = request.query_params
    if set(params) != {"date"} or len(params.getlist("date")) != 1:
        return JSONResponse({"error": "Choose one date only."}, status_code=400)
    from datetime import date
    try:
        if date.fromisoformat(params["date"]).isoformat() != params["date"]:
            raise ValueError()
    except ValueError:
        return JSONResponse({"error": "Choose a valid date."}, status_code=400)
    try:
        result = get_structured_tool_result(await call_mcp_tool("get_recovery_day_details", {"date": params["date"]}))
        if not isinstance(result, dict) or not result.get("ok"):
            raise ValueError("Unavailable day")
        data = result.get("data")
        fields = ("kind", "schema_version", "date", "timezone", "as_of", "schedule_evidence", "scope", "synthetic_demo_history", "medications", "tasks")
        if not isinstance(data, dict) or data.get("date") != params["date"]:
            raise ValueError("Invalid day")
        return JSONResponse({key: data.get(key) for key in fields}, headers={"Cache-Control": "no-store"})
    except Exception as exc:
        log("recovery_day_failed", level="error", error=exc, route="/recovery-day")
        return JSONResponse({"error": "Recovery history could not be checked."}, status_code=502, headers={"Cache-Control": "no-store"})


async def greeted(request: Request) -> JSONResponse:
    """The page has shown today's greeting (or a reminder, which greets too). Later visits
    today say "Welcome back". Only the demo patient and the patient-local date; nothing from the caller."""

    patient = get_demo_patient_context()
    try:
        state = await asyncio.to_thread(get_recovery_state, patient.patient_id) or {}
        day = get_patient_datetime(state.get("timezone") or "Europe/London").date().isoformat()
        await asyncio.to_thread(record_greeting, patient.patient_id, day)
    except Exception as exc:
        log("greeted_failed", level="error", error=exc, route="/greeted")
        return JSONResponse({"error": "Could not save the greeting."}, status_code=502)
    return JSONResponse({"ok": True}, headers={"Cache-Control": "no-store"})


async def validate_document(request: Request) -> JSONResponse:
    """Read the PDF before the upload route sends it to S3 or changes a plan."""
    chunks = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > 4 * 1024 * 1024:
            return JSONResponse({"error": "PDF must be smaller than 4 MiB."}, status_code=413)
        chunks.append(chunk)
    data = b"".join(chunks)
    if not data or b"%PDF-" not in data[:1024]:
        return JSONResponse({"error": WRONG_DOCUMENT_MESSAGE}, status_code=422)
    try:
        pages = await asyncio.to_thread(extract_pdf_text, data, max_pages=20, max_text_chars=200_000)
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


# The Reset demo route is protected by BridgeAuthenticationMiddleware.
RESET_ERROR = "Could not reset the demo. Please try again."


async def reset_demo(request: Request) -> JSONResponse:
    """
    Reset demo_patient_001 and forget this session's conversation.

    Uses the same reset as scripts/reset_demo_patient.py, which also clears
    any pending check-in. The patient is fixed on the server; the body may
    only carry the session_id whose chat memory is cleared.
    """

    if not allows_test_hooks():
        return JSONResponse({"error": "Reset is not available in production."}, status_code=403)

    try:
        body = await request.json()
    except ValueError:
        body = None

    session_id = body.get("session_id") if isinstance(body, dict) else None

    try:
        result = await asyncio.to_thread(reset_demo_patient)
    except NoPlanToReset:
        return JSONResponse({"error": "No plan to reset. Upload a letter first."}, status_code=409)
    except Exception as exc:
        log("demo_reset_failed", level="error", error=exc, route="/reset")
        return JSONResponse({"error": RESET_ERROR}, status_code=502)

    if isinstance(session_id, str) and session_id.strip():
        clear_session(session_id)

    deleted = result["events_deleted"]
    log("demo_reset", item_count=deleted)

    return JSONResponse(result, headers={"Cache-Control": "no-store"})


async def conversation(request: Request) -> JSONResponse:
    """
    The Alexa turns newer than ?after=N, for the /demo screen, and the latest id.

    Off unless ALEXA_FEED_ENABLED=true, and only with the bridge key (checked by
    BridgeAuthenticationMiddleware): it holds her words. With no `after`, no turns,
    only the latest id. Never logs the words.
    """

    if not alexa_feed.enabled():
        return JSONResponse({"error": "The Alexa feed is off."}, status_code=404)

    try:
        after = int(request.query_params["after"])
    except (KeyError, ValueError):
        after = None

    return JSONResponse(alexa_feed.since(after if after is None or after >= 0 else None),
                        headers={"Cache-Control": "no-store"})


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

    if os.getenv("LOCAL_REMINDER_LOOP") == "1" and not is_production():
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


async def bridge_health(request: Request) -> JSONResponse:
    """Public liveness only: no AWS calls or configuration/credential details."""
    return JSONResponse({"status": "ok"}, headers={"Cache-Control": "no-store"})


app = Starlette(
    routes=[
        Route("/bridge/health", bridge_health, methods=["GET"]),
        Route("/documents/validate", validate_document, methods=["POST"]),
        Route("/documents/uploaded", document_uploaded, methods=["POST"]),
        Route("/chat", chat_message, methods=["POST"]),
        # The Alexa skill endpoint (app.alexa.skill): checked, then the same turn as /chat.
        Route("/alexa", alexa_endpoint, methods=["POST"]),
        Route("/today", today, methods=["GET"]),
        Route("/week-summary", week_summary, methods=["GET"]),
        Route("/recovery-day", recovery_day, methods=["GET"]),
        Route("/tasks/complete", complete_task, methods=["POST"]),
        Route("/greeted", greeted, methods=["POST"]),
        Route("/reminders/check", check_reminder, methods=["POST"]),
        Route("/reset", reset_demo, methods=["POST"]),
        Route("/conversation", conversation, methods=["GET"]),
    ],
    lifespan=lifespan,
    middleware=[Middleware(RequestLogMiddleware), Middleware(BridgeAuthenticationMiddleware)],
)
