"""
The patient's first name, read from the letter's own "Patient" line.

Read in code, not by the model: the name is used to greet the patient, so
it must never be guessed. If the letter has no clearly labelled name, there
is no name, and AfterWard says "Good morning." without one.
"""

import re


# "Patient:", "Patient name:", "Name:", "Name of patient:" at the start of a line.
_LABEL = re.compile(r"^\s*(patient(?:'s)? name|name of patient|patient|name)\s*:\s*(.*)$", re.IGNORECASE)
# The same labels alone on a line, with no colon: a table, with the name on the next line.
_BARE_LABEL = re.compile(r"^\s*(patient(?:'s)? name|name of patient|patient|name)\s*$", re.IGNORECASE)
_TITLES = {"mr", "mrs", "ms", "miss", "mx", "dr", "prof", "professor", "sir", "dame"}
# Words from the next label in a table ("Date of birth", "Hospital no."), never part of a name.
_LABEL_WORDS = {
    "date", "birth", "dob", "hospital", "nhs", "number", "no", "id", "ward", "consultant", "surgeon",
    "admitted", "discharged", "address", "operation", "procedure", "patient", "name", "gp", "age", "sex",
}
_NAME_WORD = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ'’-]*$")


def _first_name(value: str) -> str | None:
    """'Mrs Margaret Ellis' -> 'Margaret'; 'ELLIS, Margaret' -> 'Margaret'; anything unclear -> None."""

    value = value.strip()

    # A name has no digits and is short; "SYN-0001" or a sentence is not a name.
    if not value or any(ch.isdigit() for ch in value) or value.endswith(":") or len(value) > 60:
        return None

    # "Ellis, Margaret": the given name comes after the comma.
    if "," in value:
        value = value.split(",", 1)[1]

    words = [word.strip(".") for word in value.split()]
    words = [word for word in words if word and word.lower() not in _TITLES]

    if not words or len(words) > 4 or not all(_NAME_WORD.match(word) for word in words):
        return None

    # Every word of a name starts with a capital, and none is a form label.
    if any(word[0].islower() or word.lower() in _LABEL_WORDS for word in words):
        return None

    first = words[0]

    # An initial ("M Ellis") is not a name to greet someone by.
    if len(first) < 2:
        return None

    return first.title() if first.isupper() else first


def read_first_name(document_text: str) -> str | None:
    """The first name on the letter's patient line, or None if there is no clear one."""

    lines = (document_text or "").splitlines()

    for index, line in enumerate(lines):
        match = _LABEL.match(line)

        if not match and not _BARE_LABEL.match(line):
            continue

        value = match.group(2).strip() if match else ""

        if not value:
            # The value is on the next line ("Patient:" then "Margaret Ellis").
            value = next((later.strip() for later in lines[index + 1:index + 3] if later.strip()), "")

        name = _first_name(value)

        if name:
            return name

    return None
