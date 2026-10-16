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
    action = str(sign.get("action") or "").strip()

    # The source sentence, when it also says what to do ("Call the ward ... if you have: ...").
    if snippet and (not action or " ".join(action.lower().split()) in " ".join(snippet.lower().split())):
        return _quote(snippet)

    # Otherwise the sign alone would be quoted with no one to call: join the
    # letter's two parts, in the letter's order.
    return _quote(f"{action} if you have: {snippet or sign.get('text')}")


# "Emergency services number: 555-555-0199", "Emergency number - 112": the letter's own number.
_EMERGENCY_NUMBER = re.compile(
    r"emergency[^\n.]{0,30}?(?:number|phone|telephone|line)\s*(?:is|:|-|–)?\s*(\+?\(?\d[\d\s\-()]{1,18}\d)",
    re.IGNORECASE,
)


def emergency_contact(passages: list[tuple[str, Any]]) -> dict[str, Any] | None:
    """
    The letter's emergency number, the whole line it is on and its page, from
    (text, page) passages: {"number": "555-555-0199", "line": "Emergency services
    number: 555-555-0199 (fictional number)", "page": 2}. None if the letter gives none.
    """

    for text, page in passages:
        text = text or ""
        match = _EMERGENCY_NUMBER.search(text)
        if match:
            start = text.rfind("\n", 0, match.start()) + 1
            end = text.find("\n", match.end())
            line = " ".join(text[start:end if end != -1 else len(text)].split()).lstrip("•·*-\x7f ").strip()
            return {"number": " ".join(match.group(1).split()), "line": line, "page": page}

    return None


def emergency_number(texts: list[str]) -> str | None:
    """The emergency phone number the letter gives, word for word, or None (then 999 is said)."""

    contact = emergency_contact([(text, None) for text in texts])

    return contact["number"] if contact else None


def with_emergency_line(source: dict[str, Any] | None, contact: dict[str, Any] | None) -> dict[str, Any] | None:
    """
    The letter panel's source with the letter's emergency-number line as a card of its
    own, so the number the reply says is shown in the letter's words. With no other
    source (the letter does not mention the symptom), that line is the source.
    """

    if not contact:
        return source

    card = {"text": contact["line"], "page": contact["page"], "label": "Emergency number"}

    if source is None:
        line = contact["line"]
        return {"document_id": None, "page": contact["page"], "chunk_id": None, "section": "Emergency number",
                "text": line, "highlight": line, "passage": line, "highlighted_line": line}

    # Already on screen, in the passage or a card: not shown twice.
    shown = [str(source.get("text") or ""), *(str(r.get("text") or "") for r in source.get("related") or [])]
    if any(contact["number"] in text for text in shown):
        return source

    return {**source, "related": [*(source.get("related") or []), card]}


def _call_emergency(number: str | None) -> str:
    return f"call {number}" if number else "call 999"


def warning_sign_reply(sign: dict[str, Any], first_name: str | None, number: str | None = None) -> str:
    reply = f"I'm sorry to hear that{_who(first_name)}. Your letter says: {sign_wording(sign)}"

    if number and sign.get("urgency") == "emergency" and number not in reply:
        reply += f" The emergency number in your letter is {number}."

    return reply


def letter_sentence_reply(sentence: str, first_name: str | None, number: str | None = None) -> str:
    return (
        f"I'm sorry to hear that{_who(first_name)}. Your letter says: {_quote(sentence)} "
        f"I can't give medical advice. If it's severe or sudden, {_call_emergency(number)}. "
        "Otherwise, please call NHS 111 or your care team."
    )


def no_match_reply(symptom: Symptom, first_name: str | None, number: str | None = None) -> str:
    """The fixed sentence when the letter says nothing about this symptom."""

    if "pain" in symptom.groups and symptom.part_word:
        sorry = f"I'm sorry your {symptom.part_word} hurts{_who(first_name)}"
    else:
        sorry = f"I'm sorry you're not feeling well{_who(first_name)}"

    reply = NO_MATCH_TEMPLATE.format(sorry=sorry)

    return reply.replace("call 999", _call_emergency(number))


def _same(a: dict[str, Any], b: dict[str, Any] | None) -> bool:
    return b is not None and (a is b or bool(b.get("id") and a.get("id") == b.get("id")))


def _where(sign: dict[str, Any]) -> tuple[Any, Any]:
    source = sign.get("source") or {}
    return source.get("document_id"), source.get("page")


def _warning_box(sign: dict[str, Any] | None, warning_signs: list[dict[str, Any]]) -> tuple[str, str | None]:
    """
    The letter's whole warning-signs box, rebuilt from the plan's signs on the same
    page, and the matched sign's words within it (None with no sign matched: then
    the box is anchored on the first sign). Signs that share an action are listed
    under it, as the letter does:

        Call the ward on 0000 000 000 (fictional number) if you have:
        - Pain, swelling, redness or heat in your calf.
        - A temperature of 38°C or higher.
        Call emergency services straight away if you have chest pain or ...
    """

    quoted = [s for s in warning_signs if (s.get("source") or {}).get("snippet")]
    anchor = sign if sign is not None else (quoted[0] if quoted else None)

    if anchor is None:
        return "", None

    signs = [s for s in quoted if _where(s) == _where(anchor)]

    if not any(_same(s, anchor) for s in signs):
        signs = [anchor]

    lines: list[str] = []
    highlight = sign["source"]["snippet"] if sign is not None else None
    heading = None

    for s in signs:
        snippet = s["source"]["snippet"]
        head = f"{s.get('action') or ''} if you have:"
        item = snippet[len(head):].strip() if s.get("action") and snippet.lower().startswith(head.lower()) else ""
        is_match = _same(s, sign)

        if not item:
            lines.append(snippet)
            heading = None
            continue

        if heading != head:
            lines.append(head)
            heading = head
        lines.append(f"- {item}")
        if is_match:
            highlight = item

    return "\n".join(lines), highlight


def sign_source(sign: dict[str, Any], warning_signs: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    """
    The letter panel's source for a quoted warning sign. Given the plan's warning
    signs, the panel shows the letter's whole box with this sign marked.
    """

    source = sign.get("source") or {}
    snippet = source.get("snippet")

    if not snippet:
        return None

    text, highlight = _warning_box(sign, warning_signs) if warning_signs else (snippet, snippet)

    return {
        "document_id": source.get("document_id"),
        "page": source.get("page"),
        "chunk_id": None,
        "section": "Warning signs",
        "text": text,
        "highlight": highlight,
        "passage": text,
        "highlighted_line": highlight,
    }


def warning_signs_source(
    warning_signs: list[dict[str, Any]],
    sign: dict[str, Any] | None = None,
    emergency: dict[str, Any] | None = None,
    contacts: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """
    The letter panel for a symptom: the letter's whole warning-signs box, with the
    matched sign marked (none marked when she only says she is unwell), then every
    other way to get help the letter gives. Each number is shown once:

    * the emergency line sits inside the box when the letter puts it on the same page,
      otherwise it is a card of its own;
    * other contact lines ("Switchboard: ... · Ward: ...") are one card each, and only
      when they give a number not already on screen.

    None when the letter has no quoted warning signs; the caller then falls back.
    """

    text, highlight = _warning_box(sign, warning_signs)

    if not text:
        return None

    anchor = sign if sign is not None else next(s for s in warning_signs if (s.get("source") or {}).get("snippet"))
    document_id, page = _where(anchor)
    source = {
        "document_id": document_id, "page": page, "chunk_id": None, "section": "Warning signs",
        "text": text, "highlight": highlight, "passage": text, "highlighted_line": highlight,
    }

    if emergency and emergency["number"] not in text and emergency.get("page") == page:
        source["text"] = source["passage"] = f"{text}\n{emergency['line']}"

    source = with_emergency_line(source, emergency)

    for contact in contacts or []:
        shown = " ".join([source["text"], *(str(r.get("text") or "") for r in source.get("related") or [])])
        if any(number not in shown for number in contact["numbers"]):
            source["related"] = [*(source.get("related") or []),
                                 {"text": contact["line"], "page": contact["page"], "label": "Contact numbers"}]

    return source


# A phone number: 7 or more digits, in groups ("0000 000 001", "555-555-0199", "+44 (0)20 7946 0000").
_PHONE = re.compile(r"(?<![\w/])\+?\(?\d[\d \-()]{5,}\d(?![\w/])")
# A line that gives a number to call, not one that identifies her or the letter.
_CONTACT_WORDS = re.compile(r"\b(switchboard|ward|tel|telephone|phone|helpline|contact|call|surgery|nurse|clinic|team)\b",
                            re.IGNORECASE)
_NOT_A_CONTACT = re.compile(r"\b(nhs (no|number)|hospital no|mrn|ref|date of birth|dob)\b", re.IGNORECASE)


def letter_contacts(passages: list[tuple[str, Any]]) -> list[dict[str, Any]]:
    """
    The letter's lines that give a phone number to call, word for word, from
    (text, page) passages: [{"line": "Switchboard: 0000 000 000 · Ward: 0000 000 001
    (fictional numbers)", "numbers": ["0000 000 000", "0000 000 001"], "page": 1}].
    Each line once, in the order found.
    """

    found: list[dict[str, Any]] = []

    for text, page in passages:
        for raw in (text or "").splitlines():
            line = " ".join(raw.split()).lstrip("•·*-\x7f ").strip()
            numbers = [" ".join(m.split()) for m in _PHONE.findall(line)
                       if sum(ch.isdigit() for ch in m) >= 7]
            if not numbers or not _CONTACT_WORDS.search(line) or _NOT_A_CONTACT.search(line):
                continue
            if all(f["line"] != line for f in found):
                found.append({"line": line, "numbers": numbers, "page": page})

    return found


def help_actions(warning_signs: list[dict[str, Any]], number: str | None = None) -> list[dict[str, str]]:
    """
    Who to call, in the letter's own words, for the "Get help" card.

    One line per distinct action ("Call the ward on ...", "Call emergency
    services straight away"), emergencies first. Nothing is invented: an
    action not written in the letter is never shown. The letter's emergency
    number, when it gives one, is added to its emergency action, and the
    card's call button uses it.
    """

    out = _help_actions(warning_signs)

    if number:
        emergency = next((a for a in out if a["urgency"] == "emergency"), None)
        if emergency is None:
            out.insert(0, {"urgency": "emergency", "action": f"Emergency number: {number}"})
        elif number not in emergency["action"]:
            emergency["action"] = f"{emergency['action'].rstrip('.')}: {number}"

    return out


def _help_actions(warning_signs: list[dict[str, Any]]) -> list[dict[str, str]]:

    seen: set[str] = set()
    out: list[dict[str, str]] = []

    for sign in sorted(warning_signs, key=lambda s: s.get("urgency") != "emergency"):
        action = " ".join(str(sign.get("action") or "").split())
        key = action.lower().rstrip(".")
        if not action or key in seen:
            continue
        seen.add(key)
        out.append({"urgency": str(sign.get("urgency") or "contact_care_team"), "action": action})

    return out
