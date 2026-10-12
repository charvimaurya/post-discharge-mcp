"""
Symptoms: spotting one in the patient's message, and answering only from the letter.

AfterWard never gives medical advice. When the patient says she is in pain,
dizzy, bleeding and so on, the reply is one of two things, both built here
with no model involved:

  * the letter's own warning sign and who it says to call, word for word; or
  * a fixed sentence that says the letter does not mention this, and to call
    999 if it is severe or sudden, otherwise NHS 111 or the care team.

A symptom always comes first: before a pending question, a report or a
question about the plan (see app.agent.intent).
"""

import re
from dataclasses import dataclass
from typing import Any


# What she feels. A sign in the letter and a message "match" when they share one of these.
_SYMPTOMS = {
    "pain": r"\b(pain(?!\s?(relief|killers?|medication|medicines?|tablets?))|painful|hurts?|hurting|aches?|aching|"
            r"sore|agony|throbbing|headache|migraine)\b",
    "swelling": r"\b(swelling|swollen|swell|swelled|puffy)\b",
    "redness": r"\b(red|redness|inflamed)\b",
    "heat": r"\b(heat|hot|warm|burning)\b",
    "leak": r"\b(leak\w*|ooz\w*|pus|weeping|fluid|discharge(?!\s(letter|paperwork|instructions?|summary|date)))\b",
    "bleeding": r"\b(bleed\w*|bled|blood(?!\s(thinners?|pressure|tests?)))\b",
    "fever": r"\b(fever\w*|temperature|shiver\w*|chills|feel(ing)? hot|burning up)\b",
    "breathless": r"\b(breathless\w*|short(ness)? of breath|out of breath|can(?:'?t|not) breathe|hard to breathe|"
                  r"trouble breathing|struggling to breathe|wheez\w*)\b",
    "dizzy": r"\b(dizz\w*|faint\w*|light.?headed|passed out|blacked out)\b",
    "sick": r"\b(feel(ing)? sick|been sick|being sick|was sick|vomit\w*|throwing up|threw up|nause\w*)\b",
    "fall": r"\b(fell|fallen|had a fall|have had a fall|tripped over|collapsed)\b",
    "unwell": r"\b(unwell|poorly|feel(ing)? (awful|terrible|ill|rough|weak|worse|strange|funny)|"
              r"(don'?t|not) feel(ing)? (well|right|good))\b",
    "function": r"\b(can(?:'?t|not) (move|feel|walk|stand|bend|sleep|put (any )?weight|stop)|numb\w*|tingl\w*)\b",
}
_SYMPTOMS = {name: re.compile(pattern) for name, pattern in _SYMPTOMS.items()}

# Symptoms of the whole body: where it is does not matter for a match.
_WHOLE_BODY = {"fever", "breathless", "dizzy", "sick", "fall", "unwell"}

# Where it is. "My head hurts" must not be answered with the letter's line about the calf.
_PARTS = {
    "calf": r"\b(calf|calves|legs?|shin)\b",
    "wound": r"\b(wound|scar|cut|incision|dressing|stitches|clips|staples)\b",
    "chest": r"\bchest\b",
    "head": r"\b(head|headache|migraine)\b",
    "knee": r"\bknees?\b",
    "stomach": r"\b(stomach|tummy|belly|abdomen)\b",
    "back": r"\bback\b(?! from)",
    "hip": r"\bhips?\b",
    "foot": r"\b(foot|feet|ankles?|toes?)\b",
    "arm": r"\b(arms?|hands?|shoulders?|wrists?|fingers?)\b",
    "throat": r"\bthroat\b",
    "eye": r"\beyes?\b",
}
_PARTS = {name: re.compile(pattern) for name, pattern in _PARTS.items()}

# "No pain today", "it doesn't hurt": not a symptom.
_DENIED = re.compile(
    r"\b(no|not|never|without|isn'?t|aren'?t|don'?t|doesn'?t|haven'?t|hasn'?t|didn'?t|wasn'?t)\b[^.?!,;]{0,24}$"
)
_BETTER = re.compile(r"^[^.?!,;]{0,24}\b(gone|better|fine|eased|easing|improved|improving|stopped|settled)\b")
# "It still hurts", "the pain is not going away": the denial is about it getting better.
_PERSISTS = re.compile(r"\b(not|isn'?t|won'?t|doesn'?t|hasn'?t) (going away|go away|gone away|stop\w*|eas\w*|settl\w*|improv\w*|help\w*|work\w*|control\w*)\b")
# "I took my tablets for the pain" is a report, not a new symptom.
_PURPOSE = re.compile(r"\bfor (the |my |her )?(\w+ )?pain\b")

NO_MATCH_TEMPLATE = (
    "{sorry}. Your letter doesn't mention this, and I can't give medical advice. "
    "If it's severe or sudden, call 999. Otherwise, please call NHS 111 or your care team."
)


@dataclass(frozen=True)
class Symptom:
    groups: frozenset[str]
    parts: frozenset[str]
    # Her own word for where it hurts ("head"), for the fixed sentence.
    part_word: str | None = None


def _plain(text: str) -> str:
    return text.lower().replace("’", "'")


def _features(text: str, honour_denials: bool) -> tuple[set[str], set[str], str | None]:
    plain = _plain(text)
    groups = set()

    for name, pattern in _SYMPTOMS.items():
        for match in pattern.finditer(plain):
            if honour_denials and not _PERSISTS.search(plain):
                if _DENIED.search(plain[:match.start()]) or _BETTER.search(plain[match.end():]):
                    continue
            groups.add(name)
            break

    parts = set()
    part_word = None

    for name, pattern in _PARTS.items():
        match = pattern.search(plain)
        if match:
            parts.add(name)
            part_word = part_word or ("head" if name == "head" else match.group(0))

    return groups, parts, part_word


def find_symptom(message: str, is_report: bool = False) -> Symptom | None:
    """The symptom in the patient's message, or None."""

    plain = _plain(message)

    # "I've taken my paracetamol for the pain": a report that names why.
    if is_report and _PURPOSE.search(plain):
        plain = _PURPOSE.sub(" ", plain)

    groups, parts, part_word = _features(plain, honour_denials=True)

    if not groups:
        return None

    return Symptom(frozenset(groups), frozenset(parts), part_word)


def _sign_matches(symptom: Symptom, text: str) -> int:
    """How well this letter text fits her symptom: 0 for no match, higher is closer."""

    groups, parts, _ = _features(text, honour_denials=False)
    shared = symptom.groups & groups

    if not shared:
        return 0

    if shared & _WHOLE_BODY:
        return 2 + len(shared)

    # A symptom in one place: the letter must be about the same place, or about no place at all.
    if parts:
        return 2 + len(shared) + len(symptom.parts & parts) if symptom.parts & parts else 0

    return 1 + len(shared) if not symptom.parts else 0


def match_warning_sign(symptom: Symptom, warning_signs: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The letter's warning sign for this symptom, or None. An emergency sign wins a tie."""

    best = None
    best_score = 0

    for sign in warning_signs or []:
        score = _sign_matches(symptom, str(sign.get("text") or ""))
        if score and sign.get("urgency") == "emergency":
            score += 10
        if score > best_score:
            best, best_score = sign, score

    return best


def match_letter_sentence(symptom: Symptom, sentences: list[str]) -> str | None:
    """
    A sentence found by searching the letter that is about the same symptom.

    Stricter than a warning sign: the sentence must name the same place, or
    the symptom must be a whole-body one. So "my knee hurts" is never
    answered with the medicines list's "for pain".
    """

    for sentence in sentences:
        groups, parts, _ = _features(sentence, honour_denials=False)
        shared = symptom.groups & groups

        if shared and ((symptom.parts & parts) or (shared & _WHOLE_BODY)):
            return sentence

    return None


def _who(first_name: str | None) -> str:
    return f", {first_name}" if first_name else ""


def _quote(text: str) -> str:
    text = " ".join(str(text).split())

    return text if text.endswith((".", "!", "?")) else text + "."


def sign_wording(sign: dict[str, Any]) -> str:
    """The letter's own words for this sign and what to do: its source sentence."""

    snippet = (sign.get("source") or {}).get("snippet")

    if snippet:
        return _quote(snippet)

    # No source sentence kept: the two extracted parts, in the letter's order.
    return _quote(f"{sign.get('action')} if you have: {sign.get('text')}")


def warning_sign_reply(sign: dict[str, Any], first_name: str | None) -> str:
    return f"I'm sorry to hear that{_who(first_name)}. Your letter says: {sign_wording(sign)}"


def letter_sentence_reply(sentence: str, first_name: str | None) -> str:
    return (
        f"I'm sorry to hear that{_who(first_name)}. Your letter says: {_quote(sentence)} "
        "I can't give medical advice. If it's severe or sudden, call 999. "
        "Otherwise, please call NHS 111 or your care team."
    )


def no_match_reply(symptom: Symptom, first_name: str | None) -> str:
    """The fixed sentence when the letter says nothing about this symptom."""

    if "pain" in symptom.groups and symptom.part_word:
        sorry = f"I'm sorry your {symptom.part_word} hurts{_who(first_name)}"
    else:
        sorry = f"I'm sorry you're not feeling well{_who(first_name)}"

    return NO_MATCH_TEMPLATE.format(sorry=sorry)


def sign_source(sign: dict[str, Any]) -> dict[str, Any] | None:
    """The letter panel's source for a quoted warning sign."""

    source = sign.get("source") or {}
    snippet = source.get("snippet")

    if not snippet:
        return None

    return {
        "document_id": source.get("document_id"),
        "page": source.get("page"),
        "chunk_id": None,
        "section": "Warning signs",
        "text": snippet,
        "highlight": snippet,
        "passage": snippet,
        "highlighted_line": snippet,
    }
