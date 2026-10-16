"""
The one way AfterWard writes a log line.

Every line is one JSON object on stdout:

    {"timestamp": ..., "level": ..., "service": ..., "event": ..., "request_id": ..., <fields>}

What may be logged is decided HERE, not by the caller:

  * Only field names in ALLOWED_FIELDS are kept. Anything else is dropped
    and counted (the line then carries "dropped_fields": n).
  * A kept value must be a number, a boolean, or a short code-like string
    (an id, a route, a reason code). A string with spaces or punctuation is
    dropped too, so a sentence cannot ride in on an allowed name.

So no message text, reply, letter text, quote, medicine name, dose,
patient name or patient id can reach a log line (a patient is logged as
patient_id_hash, see hash_patient). Errors go in through safe_error(),
which gives the TYPE only (see app/safe_logging.py).

request_id is kept in a contextvar, set once per request and carried from
the Next.js route to the bridge, the agent and the MCP tools.

Metrics use the CloudWatch Embedded Metric Format: the same JSON line
carries an "_aws" block, and CloudWatch turns it into a metric.
"""

import hashlib
import json
import os
import re
import sys
import time
import uuid
from contextvars import ContextVar, Token
from functools import partial
from typing import Any

from app.clock import system_now_utc
from app.safe_logging import safe_error


ALLOWED_FIELDS = frozenset({
    "event", "request_id", "session_id_hash", "patient_id_hash", "route", "status", "ms",
    "tool", "kind", "reason", "model", "tool_calls", "tokens_in", "tokens_out",
    "document_id", "stage", "item_count", "needs_confirmation_count", "checkin_type",
    "error_type", "error_code",
    # Alexa requests: the request type and intent name (codes, never her words), and whether it timed out.
    "request_type", "intent", "timed_out",
})

# name -> CloudWatch unit. A metric not listed here is dropped like any other field.
METRICS = {
    "chat_ms": "Milliseconds",
    "tool_ms": "Milliseconds",
    "upload_to_ready_ms": "Milliseconds",
    "tool_errors": "Count",
    "blocked_writes": "Count",
}
METRIC_NAMESPACE = "AfterWard"

# An id, route, code or model name: no spaces, so never a sentence.
_CODE = re.compile(r"^[A-Za-z0-9_.:#/()@+=-]{1,128}$")
_REQUEST_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")

_request_id: ContextVar[str | None] = ContextVar("afterward_request_id", default=None)
_service = os.getenv("AFTERWARD_SERVICE", "afterward")
_dropped_total = 0


def service_log(service: str):
    """log_event for one part of AfterWard: "bridge", "agent", "mcp", "document_lambda", "reminder_lambda"."""

    return partial(log_event, service=service)


def new_request_id() -> str:
    return uuid.uuid4().hex


def clean_request_id(value: str | None) -> str | None:
    """The caller's id if it looks like one, else None. Never trust a header as text."""

    return value if value and _REQUEST_ID.match(value) else None


def set_request_id(value: str | None = None) -> Token:
    """Set this request's id (a new one if none is given). Returns the reset token."""

    return _request_id.set(clean_request_id(value) or new_request_id())


def reset_request_id(token: Token) -> None:
    _request_id.reset(token)


def get_request_id() -> str | None:
    return _request_id.get()


def _short_hash(value: str | None) -> str | None:
    if not value:
        return None

    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def hash_session(session_id: str | None) -> str | None:
    """A short one-way hash, so one session's lines can be grouped without logging its id."""

    return _short_hash(session_id)


def hash_patient(patient_id: str | None) -> str | None:
    """
    A short one-way hash of a patient id, logged as patient_id_hash.

    The id itself is never a log field: one patient's lines can still be
    grouped, and found by hashing a known id, without the id in the logs.
    """

    return _short_hash(patient_id)


def dropped_fields_total() -> int:
    """How many fields this process has refused to log."""

    return _dropped_total


def _safe_value(value: Any) -> Any:
    """The value if it may be logged, else None."""

    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return round(value, 1)
    if isinstance(value, str) and _CODE.match(value):
        return value

    return None


def log_event(
    event: str,
    level: str = "info",
    error: BaseException | None = None,
    service: str | None = None,
    **fields: Any,
) -> dict:
    """
    Write one log line. Returns what was written.

        log = service_log("mcp")
        log("tool_call", tool="get_today_tasks", kind="read", status="ok", ms=41, tool_ms=41)

    error: an exception; only its type (and AWS error code) is logged.
    A field named in METRICS is also published as a CloudWatch metric.
    """

    global _dropped_total

    # The real time, never the demo clock: a log line says when it was written.
    now = system_now_utc()

    line: dict[str, Any] = {
        "timestamp": now.isoformat(timespec="milliseconds"),
        "level": level,
        "service": service or _service,
        "event": event if _CODE.match(str(event)) else "invalid_event",
        "request_id": get_request_id(),
    }

    if error is not None:
        described = safe_error(error)
        line["error_type"] = described.split("(")[0]
        if "(" in described:
            line["error_code"] = described.split("(", 1)[1].rstrip(")")

    dropped = 0
    metrics = []

    for name, value in fields.items():
        if value is None:
            continue

        allowed = name in ALLOWED_FIELDS or name in METRICS
        safe = _safe_value(value) if allowed else None

        if safe is None or name in ("event", "request_id"):
            dropped += 1
            continue

        if name in METRICS and isinstance(safe, (int, float)) and not isinstance(safe, bool):
            metrics.append({"Name": name, "Unit": METRICS[name]})

        line[name] = safe

    if dropped:
        _dropped_total += dropped
        line["dropped_fields"] = dropped

    if metrics:
        line["_aws"] = {
            "Timestamp": int(now.timestamp() * 1000),
            "CloudWatchMetrics": [{
                "Namespace": METRIC_NAMESPACE,
                "Dimensions": [["service"]],
                "Metrics": metrics,
            }],
        }

    sys.stdout.write(json.dumps(line, separators=(",", ":")) + "\n")
    sys.stdout.flush()

    return line


class Timer:
    """ms since it was made: `timer = Timer(); ...; log_event(..., ms=timer.ms)`."""

    def __init__(self) -> None:
        self._started = time.perf_counter()

    @property
    def ms(self) -> int:
        return int((time.perf_counter() - self._started) * 1000)
