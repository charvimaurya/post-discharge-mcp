"""'How long do I take them for?' about medicines she just reported: answered in code, from her plan and letter."""

import pytest

from app.agent.service import _how_long_in_code
from tests.agent.test_dose_answers import BOTH_SAVED, margaret  # noqa: F401  (fixture; its model must not be called)

PARA_LINE = ("Take 2 tablets four times a day (morning, midday, evening, bedtime) for 14 days. "
             "Take the morning dose after breakfast.")
APIX_LINE = ("Take 1 tablet twice a day (morning and evening). Take the morning dose after breakfast. "
             "Continue as directed. Your consultant will tell you how long to continue at your 6-week review.")
BOTH = ("Your paracetamol is for 14 days. For your blood thinner, the letter says your consultant will tell you "
        "how long to continue at your 6-week review.")


@pytest.fixture
def letter(margaret):  # noqa: F811
    """Margaret's medicines as the plan stores them: paracetamol has a length, apixaban does not."""

    for medicine in margaret.meds:
        if medicine["medication_id"] == "para":
            medicine.update(duration_text="for 14 days", source={"snippet": PARA_LINE, "page": 1})
        else:
            medicine.update(duration_text=None, source={"snippet": APIX_LINE, "page": 1})
    return margaret


def test_both_is_answered_word_for_word_without_the_model(letter):
    question, _ = letter.say("I have taken my medicine", fresh=True)
    assert question["response"] == "Your paracetamol, your blood thinner, or both?"

    result, writes = letter.say("I've taken both. How long do I take them for?")

    assert writes == BOTH_SAVED
    assert BOTH in result["response"]
    assert result["response"].index("as taken") < result["response"].index(BOTH) < result["response"].index("Next ")
    # The letter line shown is the medicine with no end date.
    assert result["source"]["highlight"] == APIX_LINE


# ---------- The rule itself ----------

def _turn(*medicines):
    today = {"tasks": [], "medications": list(medicines)}
    trace = [{"tool": "report_medication_taken", "arguments": {"occurrence_id": m["occurrence_id"]}, "ok": True}
             for m in medicines]
    return trace, today


PRED = {"occurrence_id": "pred#1", "medication_id": "pred", "name": "Prednisolone", "duration_text": "for 5 days",
        "source": {"snippet": "Take 8 tablets once a day with breakfast for 5 days.", "page": 1}}
COD = {"occurrence_id": "cod#1", "medication_id": "cod", "name": "Codeine", "duration_text": "Stop after 5 days.",
       "source": {"snippet": "Take 1 tablet up to four times a day. Stop after 5 days.", "page": 1}}
OMEP = {"occurrence_id": "omep#1", "medication_id": "omep", "name": "Omeprazole", "duration_text": None,
        "source": {"snippet": "Take 1 capsule once a day before breakfast.", "page": 1}}


PARA = {"occurrence_id": "para#1", "medication_id": "para", "name": "Paracetamol", "duration_text": "for 14 days",
        "source": {"snippet": PARA_LINE, "page": 1}}
APIX = {"occurrence_id": "apix#1", "medication_id": "apix", "name": "Apixaban", "duration_text": None,
        "source": {"snippet": APIX_LINE, "page": 1}}


def test_paracetamol_only():
    answer, _ = _how_long_in_code("How long do I take my paracetamol for?", *_turn(PARA))

    assert answer == "Your paracetamol is for 14 days."


def test_apixaban_only():
    answer, source = _how_long_in_code("How long do I take my blood thinner for?", *_turn(APIX))

    assert answer == ("For your blood thinner, the letter says your consultant will tell you how long to continue "
                      "at your 6-week review.")
    assert source["highlight"] == APIX_LINE


def test_a_fixed_course_like_kevins_prednisolone():
    answer, source = _how_long_in_code("How long do I take it for?", *_turn(PRED))

    assert answer == "Your prednisolone is for 5 days."
    assert source["highlight"] == PRED["source"]["snippet"]


def test_a_length_not_written_as_for_is_quoted():
    answer, _ = _how_long_in_code("When do I stop taking it?", *_turn(COD))

    assert answer == "For your codeine, the letter says: Stop after 5 days."


def test_a_medicine_with_no_length_is_never_guessed():
    answer, _ = _how_long_in_code("How long do I take it for?", *_turn(OMEP))

    assert answer == "Your letter doesn't give an end date for your omeprazole, and I won't guess."


@pytest.mark.parametrize("question", [
    "How long do I take them for, and can I drive?",   # a second question
    "How long do I take the codeine for?",              # a medicine she did not just report
    "Can I have a bath?",                               # not about how long
])
def test_anything_else_goes_to_the_model(question):
    assert _how_long_in_code(question, *_turn(PRED, OMEP)) is None


def test_nothing_saved_this_turn_goes_to_the_model():
    _, today = _turn(PRED)

    assert _how_long_in_code("How long do I take it for?", [], today) is None


# ---------- The letter panel shows the medicine's whole row from the letter ----------

# The medicines table as the letter search returns it: the name is in its own column.
TABLE_CHUNK = (
    "MEDICINES TO TAKE AT HOME\nMedicine\nHow to take it\nStatus\n"
    "1. Paracetamol 500 mg\ntablets.\n" + PARA_LINE + "\nNew\n"
    "2. Codeine 30 mg tablets.\nTake 1 tablet up to four times a day, only if needed for pain. Stop after 5 days.\nNew\n"
    "3. Apixaban 2.5 mg tablets.\n" + APIX_LINE + "\nNew\n"
)


def _letter_row(monkeypatch, search):
    import asyncio
    from app.agent import service

    async def call_tool(name, arguments):
        assert name == "search_discharge_instructions"
        return search(arguments)

    monkeypatch.setattr(service, "call_mcp_tool", call_tool)
    monkeypatch.setattr(service, "get_structured_tool_result", lambda raw: raw)
    trace = []
    saved = {"document_id": "doc", "page": 1, "chunk_id": None, "section": None,
             "text": PARA_LINE, "highlight": PARA_LINE, "passage": PARA_LINE, "highlighted_line": PARA_LINE}
    return asyncio.run(service._with_letter_row(saved, trace)), trace, saved


def test_saved_line_is_shown_as_the_letters_full_row(monkeypatch):
    source, trace, _ = _letter_row(monkeypatch, lambda arguments: {
        "ok": True, "data": [{"text": TABLE_CHUNK, "page": 1, "document_id": "doc", "chunk_id": "c1"}]})

    assert "1. Paracetamol 500 mg tablets." in source["text"]
    assert source["text"].count("tablets.") >= 3  # the other rows are shown too
    assert source["highlight"].startswith("Paracetamol 500 mg tablets.") and PARA_LINE in source["highlight"]
    assert trace == [{"tool": "search_discharge_instructions", "arguments": {"query": PARA_LINE}, "ok": True}]


@pytest.mark.parametrize("search", [
    lambda arguments: {"ok": True, "data": [{"text": "Keep the wound dry for 10 days.", "page": 1}]},
    lambda arguments: {"ok": False, "error": "insufficient evidence"},
])
def test_saved_line_stays_when_the_letter_has_no_matching_row(monkeypatch, search):
    source, _, saved = _letter_row(monkeypatch, search)

    assert source == saved


def test_saved_line_stays_when_the_search_fails(monkeypatch):
    def broken(arguments):
        raise RuntimeError("offline")

    source, trace, saved = _letter_row(monkeypatch, broken)

    assert source == saved
    assert trace[0]["ok"] is False
