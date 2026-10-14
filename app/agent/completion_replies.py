"""
Spoken replies for completion reports the code resolved itself.

These are fixed sentences filled in by code, like the reminder text,
so they never guess, never apologise for nothing, and never point at
a screen. Tone: a kind nurse, one or two short sentences.
"""

from __future__ import annotations

import re
from typing import Any

from app.agent.occurrence_resolver import everyday_name, item_name, part_of_day
from app.reminders.text import short_task_name, time_to_words


_NUMBER_WORDS = {
    1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
    6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten",
    11: "eleven", 12: "twelve", 13: "thirteen", 14: "fourteen", 15: "fifteen",
    16: "sixteen", 17: "seventeen", 18: "eighteen", 19: "nineteen", 20: "twenty",
}

WRITE_FAILED_REPLY = (
    "I couldn't record that just now. Please tell me again in a moment."
)


def _number(n: int) -> str:
    return _NUMBER_WORDS.get(n, str(n))


def _hello(first_name: str | None, opener: str) -> str:
    return f"{opener}, {first_name}." if first_name else f"{opener}."


def _noun(occurrence: dict[str, Any]) -> tuple[str, str]:
    """(singular, plural) for counting, e.g. ('walk', 'walks')."""

    name = item_name(occurrence).lower()

    if "walk" in name:
        return "walk", "walks"

    if "exercise" in name:
        return "set of exercises", "sets of exercises"

    return "one", "ones"


def medicine_name(name: str) -> str:
    """
    How a medicine is said aloud: 'paracetamol', 'blood thinner'.

    The letter's full name ("Paracetamol 500 mg tablets") stays on the screen;
    aloud, the strength and form are left out, so a dose reads naturally:
    "2 tablets of your paracetamol", not "2 tablets of your paracetamol 500 mg tablets".
    """

    everyday = everyday_name(name)

    if everyday:
        return everyday

    spoken = re.split(r"\s+\d", (name or "").strip(), maxsplit=1)[0].strip().lower()

    return spoken or (name or "medicine").lower()


def describe(occurrence: dict[str, Any]) -> str:
    """'your morning walk', 'your three o'clock walk', 'your evening paracetamol'."""

    name = item_name(occurrence)
    lowered = name.lower()

    if occurrence.get("medication_id") or occurrence.get("item_type") == "medication":
        thing = medicine_name(name)
    elif "walk" in lowered:
        thing = "walk"
    elif "exercise" in lowered:
        thing = "exercises"
    else:
        thing = lowered.split(":")[0].split(",")[0].strip()

    when = part_of_day(occurrence)

    return f"your {when} {thing}" if when else f"your {thing}"


def ask_reply(choices: list[dict[str, Any]]) -> str:
    """Which of two or more due occurrences? Named the way people speak."""

    labels = [describe(o) for o in choices]

    # Two in the same part of the day: name them by time instead.
    if len(set(labels)) < len(labels):
        labels = [
            f"your {time_to_words(str(o['clock_time']))} {describe(o).split()[-1]}"
            if o.get("clock_time") else describe(o)
            for o in choices
        ]

    if len(labels) == 2:
        options = f"{labels[0]} or {labels[1]}"
    else:
        options = ", ".join(labels[:-1]) + f" or {labels[-1]}"

    return f"Was that {options}?"


def already_done_reply(
    done: dict[str, Any],
    next_up: dict[str, Any] | None,
    first_name: str | None,
) -> str:
    """The item was already recorded and the next one is not due yet."""

    first = describe(done)
    first = first[0].upper() + first[1:]
    who = f", {first_name}" if first_name else ""
    sentence = f"{first} is already recorded{who}."

    if next_up is None:
        return f"{sentence} That's everything for today."

    if next_up.get("clock_time"):
        when = f"at {time_to_words(str(next_up['clock_time']))}"
    else:
        when = f"in the {part_of_day(next_up)}" if part_of_day(next_up) else "later today"

    return f"{sentence} Your next one is {when}."


def ask_which_medicine(choices: list[dict[str, Any]]) -> str:
    """'I took my tablets' with two medicines due: one short question."""

    names = [f"your {medicine_name(item_name(o))}" for o in choices]

    if len(names) == 2:
        return f"{names[0][0].upper()}{names[0][1:]}, {names[1]}, or both?"

    listed = ", ".join(names)

    return f"{listed[0].upper()}{listed[1:]}, or all of them?"


def not_yet_reply(
    still_to_do: list[dict[str, Any]],
    first_name: str | None,
    is_medication: bool,
) -> str:
    """
    She has not done it yet. Nothing is recorded, and we say so kindly,
    e.g. "That's okay, Margaret. Your paracetamol is still in today's plan.
    Tell me when you've taken it."
    """

    opener = _hello(first_name, "That's okay")
    after = "Tell me when you've taken it." if is_medication else "Tell me when you've done it."

    if not still_to_do:
        return f"{opener} {after}"

    if is_medication:
        names = []
        for o in still_to_do:
            spoken = f"your {medicine_name(item_name(o))}"
            if spoken not in names:
                names.append(spoken)
    else:
        names = [describe(still_to_do[0])]

    subject = " and ".join(names)
    verb = "are" if len(names) > 1 else "is"
    if len(names) > 1:
        after = after.replace(" it.", " them.")

    return f"{opener} {subject[0].upper()}{subject[1:]} {verb} still in today's plan. {after}"


_ORDINALS = {1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth"}


def reminder_ack_reply(
    reminded: dict[str, Any] | None,
    item_occurrences: list[dict[str, Any]],
    is_medication: bool,
) -> str:
    """
    She heard the reminder and is getting ready. Nothing is recorded,
    and the reminder is not repeated, e.g. "Lovely. It's the first of
    your two walks today. Tell me when you're back."
    """

    if is_medication:
        return "Lovely. Tell me when you've taken it."

    if reminded is None:
        return "Lovely. Tell me when you've done it."

    is_walk = "walk" in item_name(reminded).lower()
    ask_back = "Tell me when you're back." if is_walk else "Tell me when you've done it."
    total = len(item_occurrences)
    number = int(reminded.get("occurrence_number") or 1)

    if total >= 2 and number in _ORDINALS:
        _, plural = _noun(reminded)
        return f"Lovely. It's the {_ORDINALS[number]} of your {_number(total)} {plural} today. {ask_back}"

    return f"Lovely. {ask_back}"


# ---------- What's next: one step at a time ----------

_SLOT_WORDS = {
    "morning": "this morning", "midday": "at midday", "afternoon": "this afternoon",
    "evening": "this evening", "bedtime": "at bedtime",
}


def _words_and(names: list[str]) -> str:
    """'paracetamol and blood thinner', 'paracetamol, blood thinner and exercises'."""

    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def step_phrase(step: list[Any]) -> str:
    """
    '2 tablets of your paracetamol and 1 tablet of your blood thinner, after breakfast'
    'your knee exercises this morning'
    'your afternoon walk at three o'clock'

    A medicine is said with its dose, as on its card, so she hears how many to take.
    """

    first = step[0]

    if first.is_medication:
        names: list[str] = []
        parts: list[str] = []
        for item in step:
            name = medicine_name(item_name(item.occurrence))
            if name in names:
                continue
            names.append(name)
            dose = str(item.occurrence.get("dose") or "").strip()
            parts.append(f"{dose} of your {name}" if dose else f"your {name}")
        whens = {item.when for item in step}
        when = first.when if len(whens) == 1 else _SLOT_WORDS.get(first.slot or "", "")
        return f"{_words_and(parts)}, {when}" if when else _words_and(parts)

    return f"{first.spoken} {first.when}".strip() if first.when else first.spoken


def next_step_sentence(steps: list[list[Any]]) -> str:
    """'Next is your paracetamol and blood thinner, after breakfast.'"""

    return f"Next is {step_phrase(steps[0])}." if steps else "That's everything for today."


def after_that_sentence(steps: list[list[Any]], index: int) -> str:
    """'and after that?': the step after the one last mentioned."""

    if index >= len(steps):
        return "That's the last thing for today."

    return f"After that, {step_phrase(steps[index])}."


def day_summary(items: list[Any], first_name: str | None) -> str:
    """
    "What's left today?": one short sentence per part of the day, no counts,
    no clock times. Midday counts as afternoon and bedtime as evening.
    """

    parts = {"morning": [], "afternoon": [], "evening": []}
    belongs = {"morning": "morning", "midday": "afternoon", "afternoon": "afternoon",
               "evening": "evening", "bedtime": "evening"}

    for item in items:
        part = belongs.get(item.slot or "")
        if part is None:
            continue
        if item.is_medication:
            name = medicine_name(item_name(item.occurrence))
        else:
            name = short_task_name(item_name(item.occurrence))
        if name not in parts[part]:
            parts[part].append(name)

    openers = {"morning": "This morning", "afternoon": "This afternoon", "evening": "This evening"}
    sentences = [f"{openers[part]}, your {_words_and(names)}." for part, names in parts.items() if names]

    if not sentences:
        return everything_done(first_name)

    return " ".join(sentences)


def everything_done(first_name: str | None) -> str:
    who = f", {first_name}" if first_name else ""

    return f"That's everything for today{who}. Well done."


def completed_opener(occurrence: dict[str, Any], first_name: str | None, is_medication: bool) -> str:
    """'Well done, Margaret, that's your morning walk done.'"""

    who = f", {first_name}" if first_name else ""

    if is_medication:
        # Name exactly what was saved, dose included, so a mistake is easy to hear.
        dose = f", {occurrence['dose']}," if occurrence.get("dose") else ""
        return f"Thank you{who}, I've marked {describe(occurrence)}{dose} as taken."

    return f"Well done{who}, that's {describe(occurrence)} done."


def also_completed(occurrence: dict[str, Any], is_medication: bool) -> str:
    """The second thing in one report: 'I've also marked your morning paracetamol, 2 tablets, as taken.'"""

    if is_medication:
        dose = f", {occurrence['dose']}," if occurrence.get("dose") else ""
        return f"I've also marked {describe(occurrence)}{dose} as taken."

    return f"That's {describe(occurrence)} done too."


def after_completion_reply(
    occurrence: dict[str, Any],
    first_name: str | None,
    is_medication: bool,
    steps: list[list[Any]],
) -> str:
    """Well done, then ONLY the next step."""

    opener = completed_opener(occurrence, first_name, is_medication)

    if not steps:
        return f"{opener} That's everything for today."

    return f"{opener} {next_step_sentence(steps)}"


def whats_next_reply(first_name: str | None, steps: list[list[Any]]) -> str:
    """'What's next?': only the next step."""

    return next_step_sentence(steps) if steps else everything_done(first_name)



# ---------- Which medicines, how much, and corrections ----------

def _your(dose: dict[str, Any]) -> str:
    return f"your {medicine_name(item_name(dose))}"


def _with_dose(dose: dict[str, Any]) -> str:
    return f"{_your(dose)}, {dose['dose']}" if dose.get("dose") else _your(dose)


def _either(names: list[str], joiner: str) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + f" {joiner} " + names[-1]


def which_one_question(doses: list[dict[str, Any]]) -> str:
    """'Which one did you take: your paracetamol or your blood thinner?'"""

    return f"Which one did you take: {_either([_your(d) for d in doses], 'or')}?"


def short_dose_reply(dose: dict[str, Any]) -> str:
    """Less than the letter's dose: nothing saved, and never 'take more'."""

    return (
        f"Your letter says {dose.get('dose')} of {item_name(dose).lower()}, so I haven't marked it "
        "as done yet. Let me know when you've taken your full dose. "
        "If you're unsure, please ask your pharmacist."
    )


def saved_doses_reply(
    saved: list[dict[str, Any]],
    still_open: list[dict[str, Any]],
    first_name: str | None,
) -> str:
    """'Thank you, Margaret. I've marked your blood thinner, 1 tablet, as taken. Your paracetamol is still in today's plan.'"""

    who = f", {first_name}" if first_name else ""
    listed = [_with_dose(d) for d in saved]
    joined = listed[0] if len(listed) == 1 else ", ".join(listed[:-1]) + ", and " + listed[-1]
    comma = "," if saved[-1].get("dose") else ""
    reply = f"Thank you{who}. I've marked {joined}{comma} as taken."

    if still_open:
        names = _either([_your(d) for d in still_open], "and")
        verb = "is" if len(still_open) == 1 else "are"
        reply += f" {names[0].upper()}{names[1:]} {verb} still in today's plan."

    return reply


def undo_question(items: list[dict[str, Any]]) -> str:
    """Several were saved and she didn't say which was wrong."""

    return f"Which one should I change back: {_either([_spoken_item(i) for i in items], 'or')}?"


def undone_reply(items: list[dict[str, Any]]) -> str:
    """'Sorry about that. I've changed it back. Your blood thinner is still in today's plan.'"""

    names = _either([_spoken_item(i) for i in items], "and")
    verb = "is" if len(items) == 1 else "are"
    back = "it" if len(items) == 1 else "them"

    return f"Sorry about that. I've changed {back} back. {names[0].upper()}{names[1:]} {verb} still in today's plan."


def _spoken_item(item: dict[str, Any]) -> str:
    if item.get("medication_id") or item.get("item_type") == "medication":
        return _your(item)
    return describe(item)
