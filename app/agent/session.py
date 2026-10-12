"""
Short-lived conversation history for the AfterWard agent.

Important:
This is NOT the source of truth for the patient's recovery state.

DynamoDB/MCP remains authoritative for:
- medications
- completed tasks
- appointments
- restrictions
- recovery progress

Conversation history is only used for references such as:
    "the first one"
    "what about that medicine?"
    "and the other one?"
"""

from collections import defaultdict, deque
from typing import TypedDict


class ChatMessage(TypedDict):
    """One conversational message stored in session history."""

    role: str
    content: str


# Keep only a small amount of recent history.
#
# 12 messages ~= roughly 6 user/assistant turns.
# This keeps prompts small and inexpensive.
MAX_HISTORY_MESSAGES = 12


# In-memory store for the hackathon/demo.
#
# Example:
# {
#     "demo-session-001": deque([
#         {"role": "user", "content": "..."},
#         {"role": "assistant", "content": "..."},
#     ])
# }
_sessions: dict[str, deque[ChatMessage]] = defaultdict(
    lambda: deque(maxlen=MAX_HISTORY_MESSAGES)
)


def get_history(session_id: str) -> list[ChatMessage]:
    """
    Return recent conversation history for a session.

    A copy is returned so callers cannot mutate the
    internal deque accidentally.
    """

    return list(_sessions[session_id])


def add_message(
    session_id: str,
    role: str,
    content: str,
) -> None:
    """
    Add one message to conversation history.

    role should normally be:
        "user"
        "assistant"
    """

    _sessions[session_id].append(
        {
            "role": role,
            "content": content,
        }
    )


def clear_session(session_id: str) -> None:
    """
    Remove all conversational history for one session.

    Useful for:
    - tests
    - demo reset
    - starting a fresh conversation
    """

    _sessions.pop(session_id, None)
    _offers.pop(session_id, None)
    _saved.pop(session_id, None)
    _last_prompts.pop(session_id, None)
    _step_pointers.pop(session_id, None)

# What AfterWard has just offered in a session ("Shall I remind you
# again in 30 minutes?"), so a "yes" on the next turn can act on it.
# Kept for one turn only; DynamoDB stays the source of truth.
_offers: dict[str, dict] = {}


def set_offer(session_id: str, offer: dict) -> None:
    _offers[session_id] = offer


def pop_offer(session_id: str) -> dict | None:
    """The offer made on the previous turn, removed so it is answered once."""

    return _offers.pop(session_id, None)



# What was saved on the previous turn, so "no, I didn't take the blood
# thinner" can change exactly that back. Kept for one turn only.
_saved: dict[str, list[dict]] = {}


def set_last_saved(session_id: str, items: list[dict]) -> None:
    if items:
        _saved[session_id] = items
    else:
        _saved.pop(session_id, None)


def pop_last_saved(session_id: str) -> list[dict]:
    return _saved.pop(session_id, [])



# The step of the day last mentioned ("Next is ..."), so "and after
# that?" moves one step on each time. Reset by any new completion.
_step_pointers: dict[str, dict] = {}


# The step the last reply prompted her about ("Next is your blood thinner"), so the
# same medicine prompt is never given twice in a row unless she asks.
_last_prompts: dict[str, list[str]] = {}


def set_last_prompt(session_id: str, occurrence_ids: list[str] | None) -> None:
    if occurrence_ids:
        _last_prompts[session_id] = occurrence_ids
    else:
        _last_prompts.pop(session_id, None)


def get_last_prompt(session_id: str) -> list[str] | None:
    return _last_prompts.get(session_id)


def set_step_pointer(session_id: str, index: int, occurrence_ids: list[str]) -> None:
    _step_pointers[session_id] = {"index": index, "ids": occurrence_ids}


def get_step_pointer(session_id: str) -> dict | None:
    return _step_pointers.get(session_id)
