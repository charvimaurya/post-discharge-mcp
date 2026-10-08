"""
Small deterministic protections applied before the LLM.

Keeping certain safety rules in ordinary Python makes them
predictable and easy to unit test.
"""

import re


def remove_wake_word(message: str) -> str:
    """
    Remove the word 'Alexa' wherever it occurs.

    Examples:

        "Alexa, I'm back."
        → "I'm back."

        "Thanks, Alexa. I'm getting ready."
        → "Thanks, I'm getting ready."

    The hackathon demo specifically requires the second case.
    """

    cleaned = re.sub(
        r"\balexa\b[\s,.:;!?-]*",
        "",
        message,
        flags=re.IGNORECASE,
    )

    # Removing the wake word can leave double spaces.
    cleaned = re.sub(r"\s+", " ", cleaned)

    return cleaned.strip()

def is_ambiguous_medication_write(message: str) -> bool:
    """
    Detect obvious medication-completion statements where the
    patient has not said WHICH medicine they took.

    Example:
        "I took my medicine."

    This should NOT automatically write medication state.
    """

    text = message.lower()

    # Vague references that do not identify a specific medication.
    vague_medication_terms = [
        "my medicine",
        "my medication",
        "my tablets",
        "the medicine",
        "the medication",
    ]

    # Words suggesting that the user is reporting completion.
    completion_terms = [
        "took",
        "taken",
        "had",
    ]

    has_vague_medication = any(
        term in text
        for term in vague_medication_terms
    )

    looks_like_completion = any(
        term in text
        for term in completion_terms
    )

    return (
        has_vague_medication
        and looks_like_completion
    )

def expected_write_tool(message: str) -> str | None:
    """
    Return the write tool a completion report requires, if any.

    Examples:

        "I've taken my morning paracetamol."
        → "report_medication_taken"

        "I'm back from my walk."
        → "report_task_completed"

    Used after the LLM finishes, to catch replies that only
    read state when the patient reported doing something.
    """

    text = message.lower()

    if "?" in text:
        return None

    medication_terms = [
        "took",
        "taken",
        "have had my",
        "had my",
    ]

    task_terms = [
        "back from",
        "finished",
        "completed",
        "done my",
        "did my",
        "i've done",
        "i have done",
    ]

    if any(term in text for term in medication_terms):
        return "report_medication_taken"

    if any(term in text for term in task_terms):
        return "report_task_completed"

    return None


# Concrete calendar dates or weekdays, e.g. "23 November",
# "Monday", "23/11", "2026-11-23". Durations such as "6 weeks"
# deliberately do not match.
_MONTHS = (
    "January|February|March|April|May|June|July|August|"
    "September|October|November|December|"
    "Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
)

_DATE_PATTERN = re.compile(
    rf"\b\d{{1,2}}(?:st|nd|rd|th)?\s+(?:of\s+)?(?:{_MONTHS})\b"
    rf"|\b(?:{_MONTHS})\s+\d{{1,2}}(?:st|nd|rd|th)?\b"
    r"|\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b"
    r"|\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b"
    r"|\b\d{4}-\d{2}-\d{2}\b"
)

_APPOINTMENT_PATTERN = re.compile(
    r"\b(?:appointment|review|follow[- ]?up|clinic|consultant)s?\b",
    flags=re.IGNORECASE,
)


def mentions_date(text: str) -> bool:
    """True when text names a concrete date or weekday."""

    return bool(_DATE_PATTERN.search(text or ""))


def mentions_appointment(text: str) -> bool:
    """True when text refers to an appointment or review."""

    return bool(_APPOINTMENT_PATTERN.search(text or ""))


def strip_markdown_emphasis(text: str) -> str:
    """
    Remove **bold** / __bold__ markers.

    Replies are read aloud, so emphasis markers would be
    spoken or shown literally.
    """

    return re.sub(r"\*\*|__", "", text)
