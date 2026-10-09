"""
Local HTTP bridge between the Next.js server and the Python app.

Only the Next.js server calls this; the browser never does. The
patient comes from the server-side demo context, and nothing the
caller sends can choose the patient, date or time.
"""

import asyncio
import logging
import uuid

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from app.agent.service import chat, get_structured_tool_result
from app.clock import get_clock_label
from app.database.recovery_state import (
    clear_pending_checkin,
    get_recovery_state,
)
from app.mcp.client import call_mcp_tool
from app.mcp.context import get_demo_patient_context


logger = logging.getLogger(__name__)

TODAY_ERROR = "Could not load today's plan. Please try again."
CHAT_ERROR = "Sorry, I couldn't reach the assistant. Please try again."


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

    try:
        state = await asyncio.to_thread(
            get_recovery_state, patient.patient_id
        )
        had_checkin = bool((state or {}).get("pending_checkin"))

        result = await chat(message, session_id)
    except Exception:
        logger.exception("POST /chat failed")
        return JSONResponse({"error": CHAT_ERROR}, status_code=502)

    if had_checkin and result.get("completed"):
        try:
            await asyncio.to_thread(
                clear_pending_checkin, patient.patient_id
            )
        except Exception:
            # The reply is already real; the reminder just stays visible.
            logger.exception("Clearing pending_checkin failed")

    return JSONResponse(
        {
            "response": result["response"],
            "tool_trace": result["tool_trace"],
            "source": result["source"],
            "session_id": session_id,
        },
        headers={"Cache-Control": "no-store"},
    )


async def today(request: Request) -> JSONResponse:
    """Today's clock label, task occurrences and waiting reminder."""

    patient = get_demo_patient_context()

    try:
        # Tasks come from the MCP tool, which owns the plan rules.
        result = get_structured_tool_result(
            await call_mcp_tool("get_today_tasks", {})
        )
        state = await asyncio.to_thread(
            get_recovery_state, patient.patient_id
        )
    except Exception:
        logger.exception("GET /today failed")
        return JSONResponse({"error": TODAY_ERROR}, status_code=502)

    if not isinstance(result, dict) or not result.get("ok"):
        return JSONResponse({"error": TODAY_ERROR}, status_code=502)

    state = state or {}

    return JSONResponse(
        {
            "clock_label": get_clock_label(
                state.get("timezone") or "Europe/London"
            ),
            "tasks": result["data"]["tasks"],
            "pending_checkin": state.get("pending_checkin"),
        },
        headers={"Cache-Control": "no-store"},
    )


app = Starlette(
    routes=[
        Route("/chat", chat_message, methods=["POST"]),
        Route("/today", today, methods=["GET"]),
    ],
)
