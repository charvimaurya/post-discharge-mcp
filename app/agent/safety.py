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
        # Speech recognition often drops "the"/"my": "I have taken both medicine".
        "both medicine",
        "both medication",
        "both tablets",
        "both pills",
        "all medicine",
        "all medication",
        "all tablets",
        "all pills",
        "my pills",
        "the tablets",
        "the pills",
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
        # "Thanks Alexa, I am done with my walk": a report, not a thank-you to the reminder.
        "done with my",
        "done with the",
        "i'm done",
        "i am done",
        "all done",
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


_SCREEN_PATTERN = re.compile(r"\bscreens?\b|\bthe app\b", re.IGNORECASE)


def remove_screen_references(text: str) -> str:
    """
    Drop any sentence that mentions a screen or the app.

    Alexa+ may have no screen, so a reply must make sense when
    only heard. The prompt forbids these sentences; this makes
    sure one never reaches the patient.
    """

    sentences = re.split(r"(?<=[.!?])\s+", (text or "").strip())

    return " ".join(
        sentence
        for sentence in sentences
        if sentence and not _SCREEN_PATTERN.search(sentence)
    )


_HOLLOW_OPENER = re.compile(
    r"^\s*(you'?re|you are)\s+(absolutely\s+|quite\s+)?right\b[\s,.!:;-]*",
    re.IGNORECASE,
)


def remove_hollow_openers(text: str) -> str:
    """
    Drop a leading "You're right," and similar.

    The patient has not corrected anything, so the reply should
    start with the answer.
    """

    stripped = _HOLLOW_OPENER.sub("", text or "", count=1)

    if stripped == text:
        return text

    return stripped[:1].upper() + stripped[1:]


# ---------- Prompts she did not ask for ----------

# How a reply nudges: "next is", "when you're ready", "you still have", "have you taken".
_PROMPT_SHAPE = re.compile(
    r"\b(next|when you'?re ready|don'?t forget|remember|you (still |also )?(have|need)|have you (taken|done|had)|"
    r"it'?s time|time (for|to)|(is|are) due|still to (do|take)|left to|after that|and then|then your|"
    r"whenever you'?re ready|ready for)\b"
)
_REPLY_SENTENCE = re.compile(r"(?<=[.!?])\s+")

NOTHING_MORE_TO_SAY = "I'm here whenever you need me."


def remove_unasked_prompts(reply: str, message: str, names: list[str]) -> str:
    """
    Drop sentences that prompt her about a medicine or task she did not mention.

    Used when she neither reported anything nor asked about her plan
    ("the weather is nice"). A sentence goes only if it names one of today's
    unfinished items AND reads as a prompt, so an answer from the letter that
    happens to name a medicine is kept.
    """

    said = _plain(message)
    unasked = [name for name in names if name and name not in said]

    if not unasked or not reply:
        return reply

    kept = [
        sentence for sentence in _REPLY_SENTENCE.split(reply.strip())
        if not (
            _PROMPT_SHAPE.search(_plain(sentence))
            and any(re.search(rf"\b{re.escape(name)}\b", _plain(sentence)) for name in unasked)
        )
    ]

    return " ".join(kept).strip() or NOTHING_MORE_TO_SAY


# ---------- Negative and "not yet" answers ----------

# Phrases that contain "no" or "not" but are not a negative answer.
_NOT_A_NEGATIVE = re.compile(
    r"\b(no (problem|problems|worries|trouble|pain)|not (too )?bad)\b"
)

_NEGATIVE = re.compile(
    r"\b(no|nope|nah|not|never|"
    r"haven't|havent|hasn't|hadn't|didn't|didnt|don't|dont|"
    r"won't|wont|can't|cant|cannot|couldn't|"
    r"forgot|forgotten|forget|later|skip|skipped|skipping|missed)\b"
)


def _plain(message: str) -> str:
    """Lower case, with curly apostrophes made straight."""

    return (message or "").lower().replace("’", "'").replace("‘", "'")


def is_negative_report(message: str) -> bool:
    """
    True when the patient says she has NOT done something, or not yet.

    Examples: "no I have not taken it", "I haven't taken my blood
    thinner yet", "Not yet", "I forgot", "I'll do it later".

    Run on the message after the wake word is removed. Anything
    negative blocks every report_* write for the turn: recording a
    dose that was not taken is worse than asking again.
    """

    text = _NOT_A_NEGATIVE.sub(" ", _plain(message))

    return bool(_NEGATIVE.search(text))


_TAKE_WORDS = re.compile(r"\b(take|taken|took|tablets?|dose|medicines?|medication)\b")
_DO_WORDS = re.compile(r"\b(walk|walks|exercises?|done|back|finished)\b")


def asked_about_completion(text: str) -> str | None:
    """
    If AfterWard's last message asked whether something was done,
    the write tool it was about; otherwise None.

    "Have you taken your paracetamol yet?" -> "report_medication_taken"
    "Are you back from your walk?"          -> "report_task_completed"
    """

    text = _plain(text)

    if "?" not in text:
        return None

    if _TAKE_WORDS.search(text):
        return "report_medication_taken"

    if _DO_WORDS.search(text):
        return "report_task_completed"

    return None


# ---------- Tidy the spoken reply ----------

_LEADING_FRAGMENT = re.compile(r"^[\s—–\-….,;:]+")
_PREMATURE_PROMISE = re.compile(r"\blet me (record|mark|log|note)\b", re.IGNORECASE)


def tidy_reply(text: str) -> str:
    """
    Remove a stray leading dash or fragment and any "let me record"
    sentence, so the patient only hears a finished reply.
    """

    sentences = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    kept = " ".join(s for s in sentences if s and not _PREMATURE_PROMISE.search(s))
    kept = _LEADING_FRAGMENT.sub("", kept)

    return kept[:1].upper() + kept[1:]


# ---------- "Thanks, I'm just getting ready" ----------

_ACKNOWLEDGEMENT = re.compile(
    r"\b(thanks|thank you|cheers|ok|okay|alright|all right|sure|great|lovely|"
    r"got it|will do|on my way|getting ready|get ready|nearly ready|not ready|"
    r"not yet|in a (minute|moment|bit)|just a (minute|moment|sec)|shortly|soon)\b"
)


def is_acknowledgement(message: str) -> bool:
    """
    True for a short answer to a reminder that is not a question:
    "Thanks, I'm just getting ready", "Okay", "Not yet".
    """

    text = _plain(message)

    return "?" not in text and bool(_ACKNOWLEDGEMENT.search(text))


# ---------- "What's next?" ----------

_NEXT_UP_QUESTION = re.compile(
    r"\bwhat'?s (next|left)\b|\bwhat is (next|left)\b|\bwhat else\b|\bwhat remains\b|"
    r"\bwhat (do|should|have) i (got |need |have |got )?(to )?do\b|\bwhat now\b|"
    r"\banything else (to do|today)\b"
)

_YES = re.compile(r"^\W*(yes|yeah|yep|please|go on|go ahead|sure|ok|okay|read them|yes please)\b")


def is_next_up_question(message: str) -> bool:
    """'What's next?', 'What do I need to do now?', 'What's left today?'"""

    return bool(_NEXT_UP_QUESTION.search(_plain(message)))


def accepts_offer(message: str, last_reply: str) -> bool:
    """She said yes to 'Would you like me to read them?'."""

    return (
        "would you like me to" in _plain(last_reply)
        and bool(_YES.search(_plain(message)))
        and not is_negative_report(message)
    )


def is_permission_question(message: str) -> bool:
    """Questions about allowed activities need fresh discharge-letter evidence."""
    return bool(re.search(
        r"\b(?:am i allowed|can i|may i|could i|is it (?:safe|okay|ok)|"
        r"allowed to|permitted to|when can i|when may i)\b",
        _plain(message),
    ))


# ---------- Missed doses ----------

_AFFIRMATIVE = re.compile(
    r"^\W*(yes|yeah|yep|yup|i have|i did|i've taken|i have taken|i took|took it|taken it|done|had it|"
    r"already did|already have|already taken)\b"
)

# Questions about a missed or extra dose. Only the letter answers these.
_MISSED_DOSE_WORDS = re.compile(
    r"\b(miss(ed|ing)? (a |my |the )?(dose|tablet)|missed it|forgot|forget|forgotten|double|"
    r"two doses|take two|two tablets|extra (dose|tablet)|catch up|too late)\b"
)


# What speech recognition makes of a lone "both" (heard in testing, or close to it).
_SOUNDS_LIKE_BOTH = {"both", "boat", "boats", "bolt", "booth", "boath", "bowth", "bothe", "bot", "both of them", "both please"}


def sounds_like_both(message: str) -> bool:
    """A one-word reply that is, or sounds like, "both". Only used while a question offers "both"."""

    words = re.sub(r"[^a-z ]", "", _plain(message)).strip()

    return " ".join(words.split()) in _SOUNDS_LIKE_BOTH


def is_affirmative(message: str) -> bool:
    """'Yes', 'I have', 'I took it' as an answer to 'Have you taken it?'."""

    return bool(_AFFIRMATIVE.search(_plain(message))) and not is_negative_report(message)


def is_missed_dose_question(message: str) -> bool:
    """'Should I take two?', 'What if I missed it?', 'I forgot my dose, what now?'."""

    text = _plain(message)

    return bool(_MISSED_DOSE_WORDS.search(text)) and (
        "?" in text or text.startswith(("should", "can", "what", "do i", "is it"))
    )



# ---------- Corrections ----------

_CORRECTION = re.compile(
    r"\b(that'?s wrong|that is wrong|wrong|undo|mistake|change (it|that) back|take (it|that) back|"
    r"not true|i didn'?t (take|do|have)|i did not (take|do|have)|i haven'?t (taken|done|had))\b"
)


def is_correction(message: str) -> bool:
    """'That's wrong', 'undo that', "No, I didn't take the blood thinner"."""

    return bool(_CORRECTION.search(_plain(message)))



# ---------- One step at a time ----------

_AFTER_THAT = re.compile(
    r"\b(and )?after that\b|\bwhat'?s after (that|this)\b|\bwhat is after (that|this)\b|"
    r"\b(and )?then what\b|\bwhat comes after\b|\band next\b"
)

_WHATS_LEFT_TODAY = re.compile(
    r"\b(what'?s|what is) left (to do )?(for )?today\b|\bleft today\b|\bwhat else\b|"
    r"\brest of (the|my) day\b|\bwhat do i (still )?have (left )?today\b|\bwhat remains\b"
)


def asks_after_that(message: str) -> bool:
    """'And after that?', 'What's after that?', 'Then what?'."""

    return bool(_AFTER_THAT.search(_plain(message)))


def asks_whats_left_today(message: str) -> bool:
    """'What's left today?', 'What else do I have today?' (a bare 'What's left?' is the next step)."""

    return bool(_WHATS_LEFT_TODAY.search(_plain(message)))
