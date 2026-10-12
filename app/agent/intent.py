"""
What the patient's message is, decided in code before anything else.

Every turn starts here. The order is the rule:

    SYMPTOM  > ANSWER > REPORT > PLAN_QUESTION > FOOD > OTHER

SYMPTOM always wins, even when AfterWard has just asked a question.
ANSWER exists only while a question is waiting, and a waiting question
lasts one turn: if the message is not an answer, the question is dropped.
Next steps are offered only after a REPORT or a PLAN_QUESTION.
"""

import re
from enum import Enum
from typing import Any

from app.agent.dose_answers import count_without_name
from app.agent.food import is_food_message
from app.agent.occurrence_resolver import item_name, items_mentioned
from app.agent.safety import (
    asks_after_that,
    asks_whats_left_today,
    expected_write_tool,
    is_acknowledgement,
    is_affirmative,
    is_ambiguous_medication_write,
    is_missed_dose_question,
    is_negative_report,
    is_next_up_question,
)
from app.agent.symptoms import find_symptom


class Intent(str, Enum):
    SYMPTOM = "symptom"
    ANSWER = "answer"
    REPORT = "report"
    PLAN_QUESTION = "plan_question"
    FOOD = "food"
    OTHER = "other"


# "Both", "just the one", "the first one": an answer to "which one did you take?".
_CHOICE = re.compile(
    r"\b(both|all( of them)?|neither|none|either|one|two|three|1|2|3|"
    r"the (first|second|other|last|same) one|just the|only the|half)\b"
)
# A question about the plan: when, how many, what's due.
_ASKS = re.compile(r"\?|^\s*(when|what|which|how|do i|should i|can i|could i|is it|are there|have i|did i|am i)\b")
_PLAN_WORDS = re.compile(
    r"\b(medicines?|medications?|tablets?|pills?|doses?|blood thinners?|painkillers?|exercises?|walks?|walking|"
    r"tasks?|plan|appointments?|schedule|due|next|left|remaining|today|tonight|this (morning|afternoon|evening))\b"
)


def _plain(message: str) -> str:
    return message.lower().replace("’", "'")


def is_report(message: str, medications: list[dict[str, Any]]) -> bool:
    """'I've taken ...', 'I'm back from my walk', and 'I haven't taken ...' (a report that nothing was done)."""

    return bool(
        expected_write_tool(message.replace("?", ""))
        or is_ambiguous_medication_write(message)
        or count_without_name(message, medications)
    )


def is_answer(message: str, question: dict[str, Any] | None, items: list[dict[str, Any]]) -> bool:
    """
    Whether the message answers the waiting question.

    yes / no / not yet / a thank-you to a reminder, a count or "both", the
    name of something the question was about, or (for a missed dose) "should
    I take two?". Anything else is not an answer, and the question is dropped.
    """

    if not question:
        return False

    plain = _plain(message)

    if is_affirmative(message) or is_negative_report(message) or is_acknowledgement(message):
        return True

    if _CHOICE.search(plain):
        return True

    if question.get("type") == "missed_dose" and is_missed_dose_question(message):
        return True

    # A question of her own ("when do I take my blood thinner?") is not an answer.
    if _ASKS.search(plain):
        return False

    # She names something the question was about: "the paracetamol", "my walk".
    wanted = set(question.get("occurrence_ids") or [question.get("occurrence_id")])
    wanted |= {item.get("occurrence_id") for item in question.get("items") or []}
    asked_about = [item for item in items if item.get("occurrence_id") in wanted]

    return bool(asked_about and items_mentioned(message, [dict(item, status="pending") for item in asked_about]))


def is_plan_question(message: str, items: list[dict[str, Any]]) -> bool:
    """'What's next?', 'What's left today?', 'When do I take my blood thinner?'."""

    if is_next_up_question(message) or asks_whats_left_today(message) or asks_after_that(message):
        return True

    if is_missed_dose_question(message):
        return True

    plain = _plain(message)

    return bool(_ASKS.search(plain)) and bool(_PLAN_WORDS.search(plain) or items_mentioned(message, items))


def classify_intent(
    message: str,
    question: dict[str, Any] | None,
    today: dict[str, list] | None,
) -> Intent:
    """question: the offer or check-in waiting for her answer, if any. today: tasks and medications."""

    medications = (today or {}).get("medications") or []
    items = ((today or {}).get("tasks") or []) + medications
    report = is_report(message, medications)

    if find_symptom(message, is_report=report) is not None:
        return Intent.SYMPTOM

    if is_answer(message, question, items):
        return Intent.ANSWER

    if report:
        return Intent.REPORT

    if is_plan_question(message, items):
        return Intent.PLAN_QUESTION

    if today is not None and is_food_message(message, [str(item_name(m)) for m in medications]):
        return Intent.FOOD

    return Intent.OTHER
