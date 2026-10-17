"""
The Alexa conversation, shown on the /demo screen as it happens.

Off unless ALEXA_FEED_ENABLED=true. Kept in this process's memory only (the
last MAX_TURNS turns), never written to a log or a database: it holds her words.
"""

import copy
import os
import threading
from collections import deque

MAX_TURNS = 20

_lock = threading.Lock()
_turns: deque[dict] = deque(maxlen=MAX_TURNS)
_last_id = 0


def enabled() -> bool:
    return os.getenv("ALEXA_FEED_ENABLED", "").strip().lower() == "true"


def record(
    said: str,
    reply: str,
    source: dict | None = None,
    tool_trace: list | None = None,
    help: dict | None = None,
    crisis: bool | None = None,
    kind: str = "turn",
) -> None:
    """
    One Alexa turn: what she said, what AfterWard said back, and the rest of the turn as /chat
    returns it (the letter source, tool calls, help card, crisis), so /demo shows it the same way.
    kind: "launch" for the greeting when she opens the skill, else "turn". Nothing when the feed is off.
    """

    global _last_id

    if not enabled():
        return

    with _lock:
        _last_id += 1
        _turns.append({
            "id": _last_id, "said": said, "reply": reply, "source": source,
            "tool_trace": tool_trace or [], "help": help, "crisis": bool(crisis), "kind": kind,
        })


def since(after: int | None) -> dict:
    """
    The turns newer than id `after`, and the latest id. With no `after` (a page just
    opened), no turns: only the latest id, so the page shows what happens from now on.
    """

    with _lock:
        turns = [] if after is None else [copy.deepcopy(turn) for turn in _turns if turn["id"] > after]
        return {"turns": turns, "latest": _last_id}


def clear() -> None:
    """Forget every turn. Ids keep counting, so a page's last-seen id still works."""

    with _lock:
        _turns.clear()
