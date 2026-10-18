"""diet_advice: extracted word for word, 'avoid' or 'advice', and dropped if not in the letter."""

from discharge_letter_check.schema import load_schema

from app.ingestion.normalizer import normalize_recovery_plan
from app.ingestion.validator import validate_recovery_plan


SCHEMA = load_schema()

LETTER = """DAILY ACTIVITIES
Rest with your leg raised between activities.
DIET
- Eat plenty of fibre, such as fruit, vegetables and wholegrain bread, to help prevent constipation from your
pain medicine.
- Drink 6 to 8 glasses of water or other fluids a day.
- Do not drink alcohol while you are taking codeine.
WOUND CARE
"""

FIBRE = ("Eat plenty of fibre, such as fruit, vegetables and wholegrain bread, "
         "to help prevent constipation from your pain medicine.")
WATER = "Drink 6 to 8 glasses of water or other fluids a day."
ALCOHOL = "Do not drink alcohol while you are taking codeine."


def _extracted(*items):
    return {"discharge_date": "2026-10-16", "diet_advice": [
        {"text": text, "kind": kind, "source": {"snippet": text, "page": 1}} for text, kind in items
    ]}


def _state(*items, letter=LETTER):
    state = normalize_recovery_plan(_extracted(*items), patient_id="p", document_id="d")
    return validate_recovery_plan(state, document_text=letter)


def test_schema_has_diet_advice_with_avoid_and_advice():
    diet = SCHEMA["properties"]["diet_advice"]["items"]

    assert diet["properties"]["kind"]["enum"] == ["avoid", "advice"]
    assert set(diet["required"]) == {"text", "kind", "source"}


def test_three_letter_lines_are_kept_with_their_kind():
    state = _state((FIBRE, "advice"), (WATER, "advice"), (ALCOHOL, "avoid"))

    assert [(a.text, a.kind) for a in state.diet_advice] == [
        (FIBRE, "advice"), (WATER, "advice"), (ALCOHOL, "avoid"),
    ]
    assert not any(a.needs_confirmation for a in state.diet_advice)
    assert state.diet_advice[2].source.snippet == ALCOHOL


def test_a_reworded_or_invented_line_is_dropped():
    state = _state(
        ("Avoid alcohol while on codeine.", "avoid"),   # reworded
        ("Eat five portions of fruit a day.", "advice"),  # not in the letter
        (WATER, "advice"),
    )

    assert [a.text for a in state.diet_advice] == [WATER]


def test_a_line_broken_across_pdf_lines_still_matches():
    assert [a.text for a in _state((FIBRE, "advice")).diet_advice] == [FIBRE]


def test_unclear_wording_needs_confirmation():
    unclear = "Drink [?] glasses of water a day."
    state = _state((unclear, "advice"), letter=f"DIET\n{unclear}\n")

    assert state.diet_advice[0].needs_confirmation is True


def test_unknown_kind_needs_confirmation():
    state = _state((WATER, "maybe"))

    assert state.diet_advice[0].kind == "advice"
    assert state.diet_advice[0].needs_confirmation is True


def test_no_diet_section_means_no_diet_advice():
    state = normalize_recovery_plan({"discharge_date": "2026-10-16"}, patient_id="p", document_id="d")

    assert validate_recovery_plan(state, document_text="MEDICINES\n").diet_advice == []
