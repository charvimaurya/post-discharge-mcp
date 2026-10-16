"""
The Alexa skill and its POST /alexa route on the web bridge.

Every request is checked before it is handled: Amazon's signature and the
request timestamp (both on unless ALEXA_VERIFY_SIGNATURE / ALEXA_VERIFY_TIMESTAMP
is "false"), then the skill id, which must equal ALEXA_SKILL_ID (none set:
every request is refused). A refused request is logged with its reason.

The ask-sdk is synchronous, so the dispatch runs in a worker thread and the
handlers send run_turn back to this event loop (see app.alexa.handlers).
"""

import asyncio
import os

from ask_sdk_core.skill_builder import SkillBuilder
from ask_sdk_model import RequestEnvelope
from ask_sdk_webservice_support.verifier import RequestVerifier, TimestampVerifier, VerificationException
from ask_sdk_webservice_support.webservice_handler import WebserviceSkillHandler
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.alexa import handlers
from app.observability.log import service_log


log = service_log("alexa")


def _flag(name: str) -> bool:
    return os.getenv(name, "true").strip().lower() != "false"


def build_skill():
    builder = SkillBuilder()
    for handler in (handlers.LaunchHandler(), handlers.TaskDoneHandler(), handlers.MedicineTakenHandler(),
                    handlers.SessionEndedHandler(), handlers.ComingSoonHandler()):
        builder.add_request_handler(handler)
    builder.add_exception_handler(handlers.ErrorHandler())
    return builder.create()


_skill = build_skill()
# Checks are done in the route below, so each refusal can be logged with its reason.
_dispatcher = WebserviceSkillHandler(skill=_skill, verify_signature=False, verify_timestamp=False)


def _refuse(reason: str, status: int) -> JSONResponse:
    log("alexa_rejected", level="warning", reason=reason, status=status)
    return JSONResponse({"error": "Request refused."}, status_code=status)


async def alexa_endpoint(request: Request) -> JSONResponse:
    body = (await request.body()).decode("utf-8", errors="replace")
    headers = dict(request.headers)

    try:
        envelope = _skill.serializer.deserialize(payload=body, obj_type=RequestEnvelope)
    except Exception:
        return _refuse("bad_request", 400)

    try:
        if _flag("ALEXA_VERIFY_SIGNATURE"):
            RequestVerifier().verify(headers, body, envelope)
    except VerificationException:
        return _refuse("signature", 400)

    try:
        if _flag("ALEXA_VERIFY_TIMESTAMP"):
            TimestampVerifier().verify(headers, body, envelope)
    except VerificationException:
        return _refuse("timestamp", 400)

    expected = os.getenv("ALEXA_SKILL_ID", "").strip()
    application = getattr(getattr(envelope.context, "system", None), "application", None) if envelope.context else None
    if not expected or getattr(application, "application_id", None) != expected:
        return _refuse("skill_id", 403)

    # The handlers find this loop through the context the worker thread copies.
    handlers.BRIDGE_LOOP.set(asyncio.get_running_loop())
    reply = await asyncio.to_thread(_dispatcher.verify_request_and_dispatch, headers, body)

    return JSONResponse(reply, headers={"Cache-Control": "no-store"})
