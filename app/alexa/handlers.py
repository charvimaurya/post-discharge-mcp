"""
Alexa intent handlers: each turns what she said back into a sentence and runs
the same turn as the web chat (app.turn.run_turn), so the answers match.

The ask-sdk calls these handlers synchronously, in a worker thread (see
app.alexa.skill). run_turn is async and belongs on the bridge's own event
loop, so it is sent there with run_coroutine_threadsafe and waited for here.
"""

import asyncio
import contextvars
import os
from concurrent.futures import TimeoutError as FutureTimeout

from ask_sdk_core.dispatch_components import AbstractExceptionHandler, AbstractRequestHandler
from ask_sdk_core.utils import get_slot, is_intent_name, is_request_type
from ask_sdk_model.ui import PlainTextOutputSpeech, Reprompt

from app.database.recovery_state import get_recovery_state
from app.mcp.context import get_demo_patient_context
from app.observability.log import service_log
from app.turn import TurnFailed, run_turn


log = service_log("alexa")

# The bridge's event loop, set by the /alexa route before it hands the request to a thread.
BRIDGE_LOOP: contextvars.ContextVar[asyncio.AbstractEventLoop] = contextvars.ContextVar("bridge_loop")

# Alexa waits about 8 seconds for a reply.
TURN_TIMEOUT_SECONDS = 7.0

REPROMPT = "Anything else?"
NOT_REACHED = "Sorry, I couldn't reach the assistant. Please try again."
TOO_SLOW = "Sorry, that took too long. Please say it again."
COMING_SOON = "That part is coming soon. You can tell me what you've done, or ask what's next."

# Alexa says only which intent and slot matched, not which sample, so each opening
# phrase is its own intent: "I've had" + "my breakfast and I've taken my medicine"
# reaches the agent as she said it. Kept in step with skill-package's en-GB.json.
OPENINGS = {
    "BackFromIntent": "I'm back from",
    "DoneIntent": "I've done",
    "DidIntent": "I did",
    "FinishedIntent": "I've finished",
    "BeenForIntent": "I've been for",
    "DoneWithIntent": "I'm done with",
    "TakenIntent": "I've taken",
    "HadIntent": "I've had",
    "YesIntent": "yes",
    "BothIntent": "both",
    "JustTheIntent": "just the",
    "OnlyTheIntent": "only the",
}


def _turn(message: str, session_id: str, handler_input=None) -> str:
    """Run one turn on the bridge's loop and wait for it here; always returns something to say."""

    # Local testing only: ALEXA_ECHO_SENTENCE=true returns the sentence sent to the agent in the
    # response's session attributes. Never logged: logs hold no patient words.
    if handler_input is not None and os.getenv("ALEXA_ECHO_SENTENCE", "").strip().lower() == "true":
        handler_input.attributes_manager.session_attributes["sent_to_run_turn"] = message

    future = asyncio.run_coroutine_threadsafe(run_turn(message, session_id), BRIDGE_LOOP.get())
    try:
        return future.result(timeout=TURN_TIMEOUT_SECONDS)["response"]
    except FutureTimeout:
        log("alexa_turn_slow", level="error")
        return TOO_SLOW
    except TurnFailed as failed:
        log("alexa_turn_failed", level="error", error=failed.__cause__)
        return NOT_REACHED


def _session_id(handler_input) -> str:
    return handler_input.request_envelope.session.session_id


def _query(handler_input) -> str:
    slot = get_slot(handler_input, "query")
    return " ".join(str(slot.value or "").split()) if slot else ""


def _say(handler_input, text: str):
    """Speak text as plain text (never SSML: letter wording may hold "<" or "&"), session left open."""

    response = handler_input.response_builder.response
    response.output_speech = PlainTextOutputSpeech(text=text)
    response.reprompt = Reprompt(output_speech=PlainTextOutputSpeech(text=REPROMPT))
    response.should_end_session = False
    return response


class LaunchHandler(AbstractRequestHandler):
    """"Open after ward": the waiting reminder if there is one (left for the next turn to clear), else what's next."""

    def can_handle(self, handler_input):
        return is_request_type("LaunchRequest")(handler_input)

    def handle(self, handler_input):
        state = get_recovery_state(get_demo_patient_context().patient_id) or {}
        pending = state.get("pending_checkin") or {}

        if pending.get("text"):
            return _say(handler_input, str(pending["text"]))

        name = state.get("first_name")
        hello = f"Hello, {name}." if name else "Hello."
        return _say(handler_input, f"{hello} {_turn('What is next?', _session_id(handler_input), handler_input)}")


class OpeningHandler(AbstractRequestHandler):
    """Every "<opening words> {query}" intent: the opening words plus what followed, as one sentence."""

    def can_handle(self, handler_input):
        return any(is_intent_name(name)(handler_input) for name in OPENINGS)

    def handle(self, handler_input):
        opening = OPENINGS[handler_input.request_envelope.request.intent.name]
        message = f"{opening} {_query(handler_input)}".strip()
        return _say(handler_input, _turn(message, _session_id(handler_input), handler_input))


class MedicineAnswerHandler(AbstractRequestHandler):
    """A bare medicine name answering "...or both?": "both" (or "boat"), "the paracetamol"."""

    def can_handle(self, handler_input):
        return is_intent_name("MedicineAnswerIntent")(handler_input)

    def handle(self, handler_input):
        medicine = get_slot(handler_input, "medicine")
        message = str(medicine.value or "").strip() if medicine else ""
        return _say(handler_input, _turn(message or "both", _session_id(handler_input), handler_input))


class ComingSoonHandler(AbstractRequestHandler):
    """Every other intent, until Step 7."""

    def can_handle(self, handler_input):
        return is_request_type("IntentRequest")(handler_input)

    def handle(self, handler_input):
        return _say(handler_input, COMING_SOON)


class SessionEndedHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_request_type("SessionEndedRequest")(handler_input)

    def handle(self, handler_input):
        return handler_input.response_builder.response


class ErrorHandler(AbstractExceptionHandler):
    def can_handle(self, handler_input, exception):
        return True

    def handle(self, handler_input, exception):
        log("alexa_handler_failed", level="error", error=exception)
        return _say(handler_input, NOT_REACHED)
