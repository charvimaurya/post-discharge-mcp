"""
Replies when she says what she ate or drank. Grounded only in the letter.

AfterWard never calls a food good or bad on its own. It may:
  - quote an "avoid" line from diet_advice that clearly matches,
  - praise a choice that an "advice" line names,
  - otherwise say the letter doesn't mention it, and repeat ONE
    advice line from the letter,
  - with no diet_advice at all, say the letter gives no food advice.

If she names a meal, medicines the letter ties to that meal ("Take
the morning dose after breakfast") that are still due are asked about.

Pure: the caller fetches the plan and today's medicines.
"""

from __future__ import annotations

import re
from typing import Any

from app.agent.next_up import letter_wording
from app.agent.occurrence_resolver import everyday_name, item_name, part_of_day


# "Tea" is left out: "a cup of tea" is a drink far more often than a meal.
MEALS = {"breakfast": "morning", "lunch": "midday", "dinner": "evening", "supper": "evening"}

# Everyday words, grouped so "wine" can match a letter line about "alcohol"
# and "banana" one about "fruit". Recognising words only; never a rule.
_GROUPS = {
    "alcohol": {"alcohol", "alcoholic", "wine", "beer", "lager", "cider", "gin", "whisky", "whiskey",
                "vodka", "rum", "sherry", "port", "pint", "prosecco", "champagne"},
    "fruit": {"fruit", "banana", "apple", "orange", "pear", "berries", "grapes", "plum", "prunes"},
    "vegetables": {"vegetables", "veg", "salad", "carrots", "broccoli", "peas", "beans"},
    "fibre": {"fibre", "fiber", "porridge", "oats", "bran", "wholemeal", "wholegrain", "brown bread",
              "fruit", "vegetables", "prunes", "beans"},
    "water": {"water", "fluids", "fluid"},
    "caffeine": {"caffeine", "coffee", "tea", "cola"},
}

_FOODS = {
    "pizza", "porridge", "toast", "cereal", "sandwich", "soup", "chips", "cake", "biscuit", "biscuits",
    "egg", "eggs", "bacon", "sausage", "sausages", "curry", "pasta", "rice", "chicken", "fish", "steak",
    "burger", "chocolate", "crisps", "yoghurt", "yogurt", "bread", "cheese", "milk", "juice", "coffee",
    "tea", "water", "wine", "beer", "lager", "cider", "gin", "whisky", "vodka", "banana", "apple",
    "orange", "fruit", "salad", "vegetables", "beans", "oats", "prunes", "noodles", "pie", "roast",
}
_FOODS |= set().union(*_GROUPS.values())

_EATING = re.compile(
    r"\b(ate|eaten|eating|eat|drank|drunk|drinking|had|having|have had|just had|"
    r"for (breakfast|lunch|dinner|tea|supper))\b"
)

# A food report is never one of these: they go the usual way.
_NOT_FOOD = re.compile(
    r"\b(sick|vomit\w*|nause\w*|can't keep|cannot keep|keep (it|food|anything) down|"
    r"pain|fall|fell|bleed\w*|walk|exercises?|tablets?|dose|medicine|medication|pill)\b"
)


def _plain(message: str) -> str:
    return (message or "").lower().replace("’", "'")


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z]+", _plain(text)))


def meals_named(message: str) -> list[str]:
    """'pizza for breakfast' -> ['breakfast']."""

    text = _plain(message)

    return [meal for meal in MEALS if re.search(rf"\b{meal}\b", text)]


def foods_named(message: str) -> list[str]:
    """Foods and drinks she named, in the order she said them."""

    text = _plain(message)
    found = []

    for word in re.findall(r"[a-z]+", text):
        if word in _FOODS and word not in found and word not in MEALS:
            found.append(word)

    return found


_ABOUT_FOOD = re.compile(r"\b(eat|eating|drink|drinking|food|diet|meals?)\b")


def is_food_message(message: str, medicine_names: list[str] = ()) -> bool:
    """
    About food or drink: a report ('I ate pizza for breakfast'), a question
    ('what can I eat?', 'can I have wine?'), a plan or a 'not yet'.
    Not a medicine report, a walk, or a warning sign.
    """

    text = _plain(message)

    if _NOT_FOOD.search(text):
        return False

    if any(name and name.lower() in text for name in medicine_names):
        return False

    named = foods_named(text) or meals_named(text)

    if named:
        # A report, plan, question or "not yet" about a named meal or food.
        return bool(
            _EATING.search(text) or foods_named(text) or _PLAN.search(text)
            or _NOT_YET.search(text) or _QUESTION.search(text) or _ABOUT_FOOD.search(text)
        )

    # "What can I eat?" names no food, but is still about food.
    return classify_food_message(text) == QUESTION and bool(_ABOUT_FOOD.search(text))


# ---------- What kind of food message is it? ----------

ATE, QUESTION, PLAN, NOT_YET = "ate", "question", "plan", "not_yet"

_NOT_YET = re.compile(
    r"\b(haven'?t|have not|hasn'?t|didn'?t|did not|not)\b[^.?!]*\b(had|eaten|eat|ate|yet)\b"
    r"|\bno (breakfast|lunch|dinner|supper)\b|\bnot (eaten|had)\b|\bnothing to eat\b"
)
_QUESTION = re.compile(
    r"\b(what can i|what should i|what do i|what to|can i|could i|may i|should i|"
    r"is it (ok|okay|alright|all right|safe|fine)|am i allowed|are .* allowed|do i need to)\b"
)
_PLAN = re.compile(
    r"\b(going to (have|eat|drink)|gonna|about to|i'?ll (have|eat|drink)|i will (have|eat|drink)|"
    r"i'?m having|having (my |some )?(breakfast|lunch|dinner|supper)|"
    r"(making|getting|fixing) (my |some )?(breakfast|lunch|dinner|supper))\b"
)
_ATE = re.compile(r"\b(ate|eaten|had|have had|i'?ve had|just had|finished|drank|drunk)\b")


def classify_food_message(message: str) -> str:
    """
    ATE ('I ate', 'I had', 'just finished breakfast'), QUESTION ('what can I
    eat', 'can I have', anything ending in '?'), PLAN ('about to have',
    'having breakfast now') or NOT_YET ("I haven't had breakfast").

    Anything unclear is a QUESTION: AfterWard never assumes she ate.
    """

    text = _plain(message)

    if _NOT_YET.search(text):
        return NOT_YET
    if "?" in text or _QUESTION.search(text):
        return QUESTION
    if _PLAN.search(text):
        return PLAN
    if _ATE.search(text):
        return ATE
    return QUESTION


def _groups_of(word: str) -> set[str]:
    return {group for group, members in _GROUPS.items() if word in members} | {word}


def _mentions(advice_text: str, food: str) -> bool:
    """Does this letter line name the food, or a group it belongs to ('wine' -> 'alcohol')?"""

    words = _words(advice_text)
    lowered = _plain(advice_text)

    return any(term in words or (" " in term and term in lowered) for term in _groups_of(food))


def diet_reply(message: str, diet_advice: list[dict[str, Any]], first_name: str | None) -> str:
    """The food part of the reply: match, fits, not mentioned, or no advice at all."""

    who = f", {first_name}" if first_name else ""
    thanks = f"Thanks for telling me{who}."

    if not diet_advice:
        return f"{thanks} Your letter doesn't give any advice about food."

    foods = foods_named(message)
    advice = [a for a in diet_advice if str(a.get("text") or "").strip()]

    # a) An "avoid" line that clearly matches: quote it, gently.
    for food in foods:
        for item in advice:
            if item.get("kind") == "avoid" and _mentions(item["text"], food):
                return f"{thanks} Your letter says: {item['text'].strip()}"

    # c) It fits an "advice" line: short praise, with the line it fits.
    for food in foods:
        for item in advice:
            if item.get("kind") == "advice" and _mentions(item["text"], food):
                return f"That sounds good{who}. Your letter says: {item['text'].strip()}"

    # b) Not in the letter: never call it bad; repeat one piece of advice.
    general = next((a for a in advice if a.get("kind") == "advice"), advice[0])
    named = foods[0] if foods else "that"
    not_mentioned = (
        f"Your letter doesn't mention {named}." if foods else "Your letter doesn't mention that."
    )

    return f"{thanks} {not_mentioned} It does say: {general['text'].strip()}"


def medicines_for_meal(meal: str, medications: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Today's still-due doses the letter ties to this meal, e.g. "Take the
    morning dose after breakfast" for breakfast. One dose per medicine.
    """

    found: dict[str, dict[str, Any]] = {}

    for dose in medications:
        if dose.get("as_needed") or dose.get("status") == "completed":
            continue

        slot = part_of_day(dose)
        wording = letter_wording(dose).get(slot or "", "")

        if meal in wording:
            found.setdefault(str(dose.get("medication_id") or item_name(dose)), dose)

    return list(found.values())


def _spoken_dose(dose: dict[str, Any]) -> str:
    name = everyday_name(item_name(dose)) or item_name(dose).lower()
    return f"your {name}, {dose['dose']}" if dose.get("dose") else f"your {name}"


def meal_medicines_question(meal: str, doses: list[dict[str, Any]]) -> str:
    """'Now that you've had breakfast, it's time for ... . Have you taken them?'"""

    names = [_spoken_dose(d) for d in doses]
    listed = names[0] if len(names) == 1 else ", ".join(names[:-1]) + ", and " + names[-1]
    them = "it" if len(doses) == 1 else "them"

    return f"Now that you've had {meal}, it's time for {listed}. Have you taken {them}?"


NO_FOOD_ADVICE_ANSWER = (
    "Your letter doesn't give any advice about food. If you're unsure, please ask your care team."
)


def food_question_reply(message: str, diet_advice: list[dict[str, Any]]) -> str:
    """
    "What can I eat?" / "Can I have wine?": only the letter's own lines.
    Never a yes or no of AfterWard's own, never a food the letter doesn't name.
    """

    advice = [a for a in diet_advice if str(a.get("text") or "").strip()]

    if not advice:
        return NO_FOOD_ADVICE_ANSWER

    foods = foods_named(message)

    if not foods:
        # A general question: the letter's diet lines, quoted (at most three).
        return "Your letter says: " + " ".join(a["text"].strip() for a in advice[:3])

    for food in foods:
        for kind in ("avoid", "advice"):
            for item in advice:
                if item.get("kind") == kind and _mentions(item["text"], food):
                    return f"Your letter says: {item['text'].strip()}"

    general = next((a for a in advice if a.get("kind") == "advice"), advice[0])

    return f"Your letter doesn't mention {foods[0]}. It does say: {general['text'].strip()}"


def meal_medicines_reminder(meal: str, doses: list[dict[str, Any]]) -> str:
    """
    For a plan or a 'not yet': a reminder, never a question.
    'Remember, your paracetamol, 2 tablets, and your blood thinner, 1 tablet, are taken after breakfast.'
    """

    names = [_spoken_dose(d) for d in doses]
    listed = names[0] if len(names) == 1 else ", ".join(names[:-1]) + ", and " + names[-1]
    wording = next(
        (letter_wording(d).get(part_of_day(d) or "", "") for d in doses
         if meal in letter_wording(d).get(part_of_day(d) or "", "")),
        f"after {meal}",
    )
    verb = "is" if len(doses) == 1 else "are"
    # "your blood thinner, 1 tablet, are taken": close the dose with a comma.
    comma = "," if doses[-1].get("dose") else ""

    return f"Remember, {listed}{comma} {verb} taken {wording}."
