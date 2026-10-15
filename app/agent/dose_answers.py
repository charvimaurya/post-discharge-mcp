"""
Read her answer to "Have you taken them?" before anything is saved.

A dose is saved only when it is clear WHICH medicine and that the FULL
dose was taken:

- "all of them" only for a plain yes: "yes", "yes I have", "I've taken
  them", "both".
- A number ("one", "1"), "only", "just", "one of them", "but", or naming
  only some medicines: only the named ones; if none is named, ask which.
- A stated number below the letter's dose (1 tablet when the letter says
  2): not saved. AfterWard never tells her to take more.

Pure: no AWS, no model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.agent.occurrence_resolver import everyday_name, item_name


_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "a": None}
_NUMBER = re.compile(r"\b([1-9]|one|two|three|four)\b")
_NEGATION = {"not", "didn't", "didnt", "haven't", "havent", "no", "without", "forgot", "never", "hasn't"}
_PARTIAL = re.compile(r"\b(only|just|one of them|some of them|but|half)\b")
_PLAIN_ALL = re.compile(
    r"^\W*(yes|yeah|yep|yup)?\W*(both( of them)?|all( of them)?|i('?ve| have) taken (them|both|all)|"
    r"took them|taken them|i have|i did|i('?ve| have) had them|done|yes)?\W*(both|please|thanks)?\W*$"
)
# "I have taken both the medicines", "I took all my tablets": "both" or "all" with a taken word.
_TOOK_ALL = re.compile(
    r"\b(took|taken|had|done)\b.*\b(both|all( of)? (them|my \w+|the \w+))\b"
)
# The letter's dose as a count of tablets, capsules or similar: "2 tablets" -> 2.
_DOSE_COUNT = re.compile(r"^\s*(\d+)\s*(tablet|capsule|caplet|pill|sachet)s?\b", re.IGNORECASE)


@dataclass
class DoseAnswer:
    """
    kind:
        "all"   save every dose asked about
        "some"  save `take`; `short` were named with less than the letter's dose
        "ask"   unclear which: ask, remembering `stated` (a number she said)
        "none"  she has not taken them
    """

    kind: str
    take: list[dict[str, Any]] = field(default_factory=list)
    short: list[tuple[dict[str, Any], int]] = field(default_factory=list)
    stated: int | None = None
    # A number, "only", "just", "one of them": an answer, but not a clear one.
    partial: bool = False


def _plain(text: str) -> str:
    return (text or "").lower().replace("’", "'")


# "one of them" means one medicine, not one tablet.
_ONE_OF = re.compile(r"\bone of (them|those|the two|my tablets|my medicines)\b")


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", _ONE_OF.sub(" ", _plain(text)))


def letter_dose_count(dose: dict[str, Any]) -> int | None:
    """'2 tablets' -> 2. None when the dose is not a simple count (e.g. '10 ml')."""

    match = _DOSE_COUNT.match(str(dose.get("dose") or ""))

    return int(match.group(1)) if match else None


def _names(dose: dict[str, Any]) -> list[list[str]]:
    """How she might say this medicine: ['paracetamol'], ['blood', 'thinner'], ['apixaban']."""

    names = [item_name(dose).lower()]
    everyday = everyday_name(item_name(dose))
    if everyday:
        names.append(everyday)

    return [_tokens(name) for name in names if name]


def _mentions(tokens: list[str], dose: dict[str, Any]) -> list[int]:
    """Token positions where this medicine is named."""

    found = []

    for name in _names(dose):
        size = len(name)
        for i in range(len(tokens) - size + 1):
            if tokens[i:i + size] == name:
                found.append(i)

    return sorted(found)


def _number_at(tokens: list[str], position: int) -> int | None:
    """A number said just before or just after a mention ('one paracetamol', 'paracetamol, one tablet')."""

    window = list(range(max(0, position - 3), position)) + list(range(position + 1, min(len(tokens), position + 4)))

    for i in sorted(window, key=lambda j: abs(j - position)):
        word = tokens[i]
        if word.isdigit() and 1 <= int(word) <= 9:
            return int(word)
        if _NUMBERS.get(word):
            return _NUMBERS[word]

    return None


def _negated(tokens: list[str], position: int) -> bool:
    """'not the blood thinner', "didn't take the blood thinner"."""

    return any(word in _NEGATION for word in tokens[max(0, position - 4):position])


def _numbers_said(tokens: list[str]) -> list[int]:
    out = []
    for word in tokens:
        if word.isdigit() and 1 <= int(word) <= 9:
            out.append(int(word))
        elif _NUMBERS.get(word):
            out.append(_NUMBERS[word])
    return out


def parse_dose_answer(
    message: str,
    doses: list[dict[str, Any]],
    carried: int | None = None,
    negative: bool = False,
) -> DoseAnswer:
    """
    Which of `doses` (one per medicine, asked about together) to save.

    carried: a number she said on the previous turn ("I have taken one
    tablet"), applied when she now names a single medicine.
    negative: the message reads as "no / not yet" overall.
    """

    tokens = _tokens(message)
    named: list[tuple[dict[str, Any], int]] = []
    negated: list[dict[str, Any]] = []

    for dose in doses:
        positions = _mentions(tokens, dose)
        if not positions:
            continue
        if all(_negated(tokens, p) for p in positions):
            negated.append(dose)
        else:
            named.append((dose, next(p for p in positions if not _negated(tokens, p))))

    numbers = _numbers_said(tokens)

    # One medicine asked about and a clear "I took ..." with no name: it is that one.
    if not named and not negated and len(doses) == 1 and not negative and (
        numbers or re.search(r"\b(took|taken|had|have|did|yes)\b", _plain(message))
    ):
        named = [(doses[0], -1)]

    if named:
        answer = DoseAnswer(kind="some")
        for dose, position in named:
            said = _number_at(tokens, position) if position >= 0 else None
            if said is None and len(named) == 1:
                said = numbers[0] if len(numbers) == 1 else carried
            needed = letter_dose_count(dose)
            if said is not None and needed is not None and said < needed:
                answer.short.append((dose, said))
            else:
                answer.take.append(dose)
        return answer

    if negated or negative:
        return DoseAnswer(kind="none")

    partial = bool(numbers) or bool(_PARTIAL.search(_plain(message))) or bool(_ONE_OF.search(_plain(message)))

    if not partial and (_PLAIN_ALL.match(_plain(message)) or _TOOK_ALL.search(_plain(message))) and _plain(message).strip(" .!"):
        return DoseAnswer(kind="all", take=list(doses))

    return DoseAnswer(kind="ask", stated=numbers[0] if len(numbers) == 1 else carried, partial=partial)


def stated_count_for(message: str, dose: dict[str, Any]) -> int | None:
    """The number of tablets she says she took of this one medicine, if she says one."""

    tokens = _tokens(message)
    positions = _mentions(tokens, dose)
    numbers = _numbers_said(tokens)

    for position in positions:
        said = _number_at(tokens, position)
        if said is not None:
            return said

    return numbers[0] if len(numbers) == 1 and re.search(r"\b(tablets?|capsules?|pills?)\b", _plain(message)) else None


def is_short_dose(message: str, dose: dict[str, Any]) -> int | None:
    """The number she said, if it is less than the letter's dose; otherwise None."""

    said = stated_count_for(message, dose)
    needed = letter_dose_count(dose)

    return said if said is not None and needed is not None and said < needed else None


# ---------- The write guard: every report_medication_taken passes here ----------

_A_TABLET = re.compile(r"\ba (tablet|pill|capsule|caplet)\b")


def _says_a_count(message: str) -> bool:
    """'one', '1', 'a tablet', 'only', 'just', 'one of them'."""

    text = _plain(message)

    return bool(
        _numbers_said(_tokens(message))
        or _PARTIAL.search(text)
        or _ONE_OF.search(text)
        or _A_TABLET.search(text)
    )


def write_refusal(
    message: str,
    dose: dict[str, Any],
    question: dict[str, Any] | None = None,
    negative: bool = False,
    others: list[dict[str, Any]] = (),
) -> tuple[str, str] | None:
    """
    Why this report_medication_taken must NOT be written, or None to allow it.

    ("not_taken", ...)  she said she has not taken it
    ("which", ...)      she gave a count but did not name this medicine
    ("short", ...)      her count is below the letter's dose

    question: the question she is answering (it may carry a count she
    gave earlier, e.g. "I have taken one tablet").
    others: today's other medicines; naming only another one means not this.
    """

    tokens = _tokens(message)
    positions = _mentions(tokens, dose)
    named = [p for p in positions if not _negated(tokens, p)]

    if positions and not named:
        return "not_taken", "She said she has not taken this medicine."

    if negative and not named:
        return "not_taken", "She said she has not taken it."

    if _says_a_count(message) and not named:
        return "which", "She gave a count but did not say which medicine. Ask which one she took."

    if not named and any(
        other.get("medication_id") != dose.get("medication_id") and _mentions(tokens, other)
        for other in others
    ):
        return "which", "She named a different medicine, not this one."

    said = None
    if named:
        said = _number_at(tokens, named[0])
        if said is None:
            numbers = _numbers_said(tokens)
            said = numbers[0] if len(numbers) == 1 else None
    if said is None and not _numbers_said(tokens) and question:
        said = question.get("stated")
    if said is None and _A_TABLET.search(_plain(message)):
        said = 1

    needed = letter_dose_count(dose)

    if said is not None and needed is not None and said < needed:
        return "short", f"She said {said}, but her letter says {dose.get('dose')}. Do not record it."

    return None


def count_without_name(message: str, doses: list[dict[str, Any]]) -> bool:
    """'I've taken one tablet': a count, but no medicine named."""

    tokens = _tokens(message)

    return _says_a_count(message) and not any(_mentions(tokens, dose) for dose in doses)


def stated_count(message: str) -> int | None:
    """The one number she said ('one tablet' -> 1, 'a tablet' -> 1), if exactly one."""

    numbers = _numbers_said(_tokens(message))

    if len(numbers) == 1:
        return numbers[0]

    return 1 if not numbers and _A_TABLET.search(_plain(message)) else None
