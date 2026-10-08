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