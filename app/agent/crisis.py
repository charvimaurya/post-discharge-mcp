"""
Crisis: the patient says she may harm herself.

Checked first on every turn, before anything else (app.agent.service).
The reply is fixed text, with no model, no MCP tool and nothing saved.
AfterWard never answers a question about how much medicine would cause harm.

Matching is on whole phrases, after the message is put in lower case with
punctuation removed and spaces collapsed. "kill" alone never matches, so
"kill the reminder" is an ordinary message.
"""

import re


_NOT_WORDS = re.compile(r"[^a-z0-9 ]+")

_MEDICINE = r"(tablets?|pills?|paracetamols?|codeine|apixaban|painkillers?|medicines?|medications?|meds)"

_PHRASES = [
    # Direct
    r"kill (myself|my self)", r"end my (own )?life", r"take my (own )?life", r"end it all",
    r"suicid\w*", r"(want|wanna|wish|like) to die", r"wish i (was|were) dead",
    r"(hurt|harm|harming|hurting) (myself|my self)", r"self harm\w*",
    # Slang
    r"kms", r"kys",
    # Indirect
    r"better off without me", r"(dont|do not|cant|cannot) see the point",
    r"no point (in )?(going|carrying) on", r"take all (of )?(my|the|these|those) (tablets|pills)",
    # Asking how much medicine would cause harm
    r"how (many|much)\b.{0,60}\b(hurt|harm|kill|damage) me",
    r"how (many|much)\b.{0,60}\b(to|would|will|is|are) (die|overdose|be fatal|be lethal|an overdose)",
    r"(lethal|fatal|deadly) (dose|amount)",
    rf"enough {_MEDICINE}? ?to (kill|hurt|harm|end)",
    rf"overdose on (my |the )?{_MEDICINE}",
]
_CRISIS = re.compile(r"\b(?:" + "|".join(_PHRASES) + r")\b")

# After a crisis reply, a question about doses or tablet counts is never answered.
_DOSE_QUESTION = re.compile(
    rf"\b(how (many|much)|maximum|max|most|safe (dose|amount)|doses?|dosage|overdose|"
    rf"{_MEDICINE} (can|could|should|do|would) i (take|have))\b"
)

HELP = "If you might act on it now, call 999. You can talk to Samaritans any time on 116 123, free."
CHECK_IN = "Before we carry on, how are you feeling now?"


def normalise(message: str) -> str:
    """Lower case, no punctuation, single spaces: "DON'T  see the point!!" -> "dont see the point"."""

    text = (message or "").lower().replace("’", "").replace("'", "")

    return " ".join(_NOT_WORDS.sub(" ", text).split())


def is_crisis(message: str) -> bool:
    return bool(_CRISIS.search(normalise(message)))


def asks_about_doses(message: str) -> bool:
    """'How many tablets can I take?', 'what's the maximum dose?'."""

    return bool(_DOSE_QUESTION.search(normalise(message)))


def crisis_reply(first_name: str | None) -> str:
    who = f", {first_name}" if first_name else ""

    return (
        f"I'm really sorry you're feeling this way{who}. "
        f"You don't have to go through this alone. {HELP}"
    )


def check_in_reply() -> str:
    """The turn after a crisis reply, when she asks about her plan."""

    return f"{CHECK_IN} {HELP}"
