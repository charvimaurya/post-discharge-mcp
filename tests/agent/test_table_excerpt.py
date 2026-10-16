"""A medicines table is shown as the letter's rows, with the row that answers marked."""

from app import turn
from app.agent.evidence import clean_passage, select_rag_source


TABLE = (
    "stable. The wound was clean and dry on the day of discharge. Margaret is safe to go home and manage the\n"
    "stairs with one rail.\nMEDICINES TO TAKE AT HOME\n Medicine\nHow to take it\nStatus\n"
    "1. Paracetamol 500 mg\ntablets.\nTake 2 tablets four times a day (morning, midday, evening, bedtime) for 14\n"
    "days. Take the morning dose after breakfast.\nNew\n"
    "2. Codeine 30 mg tablets.\nTake 1 tablet up to four times a day, only if needed for pain. Stop after 5 days.\nNew\n"
    "3. Apixaban 2.5 mg tablets.\nTake 1 tablet twice a day (morning and evening). Take the morning dose after\n"
    "breakfast. Continue as directed.\nNew\n"
    "4. Senna 7.5 mg tablets.\nTake 2 tablets at bedtime if constipated.\nNew\nUsual medicines before admission: no"
)
APIXABAN_ROW = (
    "Apixaban 2.5 mg tablets. Take 1 tablet twice a day (morning and evening). "
    "Take the morning dose after breakfast. Continue as directed."
)
REPLY = "Your letter says to continue your blood thinner as directed, but doesn't state a specific end date."
QUESTION = "How long do I take my blood thinner for?"


def table_source():
    match = {"text": TABLE, "page": 1, "document_id": "d", "chunk_id": "c", "distance": 0.3}
    return select_rag_source(REPLY, [match], context_texts=[QUESTION], entity_names=["Apixaban 2.5 mg tablets"])


def test_the_column_headings_are_never_the_excerpt():
    source = table_source()

    assert "Medicine How to take it Status" not in source["text"]
    assert source["highlight"] != "Medicine How to take it Status"
    assert source["section"] == "Medicines To Take At Home"


def test_every_row_is_shown_and_the_blood_thinner_row_is_marked():
    source = table_source()

    assert source["text"].split("\n") == [
        "1. Paracetamol 500 mg tablets. Take 2 tablets four times a day (morning, midday, evening, bedtime) "
        "for 14 days. Take the morning dose after breakfast.",
        "2. Codeine 30 mg tablets. Take 1 tablet up to four times a day, only if needed for pain. Stop after 5 days.",
        f"3. {APIXABAN_ROW}",
        "4. Senna 7.5 mg tablets. Take 2 tablets at bedtime if constipated.",
    ]
    assert source["highlight"] == APIXABAN_ROW


def test_the_status_cell_is_not_shown_as_part_of_a_sentence():
    assert " New" not in table_source()["text"]


def test_a_numbered_list_without_column_headings_keeps_its_words():
    plain = "MEDICINES\n1.\nApixaban 2.5 mg tablets. Take 1 tablet twice a day. New dose from today\n2.\nSenna 7.5 mg tablets. At bedtime."
    excerpt = clean_passage(plain, "blood thinner twice a day")

    # No headings line above the list, so this is not a table: nothing after the last sentence is cut.
    assert excerpt["text"] == "1. Apixaban 2.5 mg tablets. Take 1 tablet twice a day. New dose from today"


# ---------- The "no end date" note ----------

STATE = {
    "discharge_date": "2026-10-16",
    "medications": [
        {"name": "Paracetamol 500 mg tablets", "duration_text": "for 14 days", "as_needed": False},
        {"name": "Codeine 30 mg tablets", "duration_text": "Stop after 5 days.", "as_needed": True},
        {"name": "Apixaban 2.5 mg tablets", "duration_text": "Continue as directed", "as_needed": False},
        {"name": "Senna 7.5 mg tablets", "duration_text": None, "as_needed": True},
    ],
}
NOTE = {"flag": turn.NO_END_DATE_FLAG, "text": turn.NO_END_DATE_TEXT}


def marked(row):
    return {"text": row, "highlight": row}


def test_note_when_she_asks_how_long_and_the_letter_gives_no_end():
    assert turn.open_ended_medicine_note(marked(APIXABAN_ROW), f"{QUESTION} {REPLY}", STATE) == NOTE


def test_no_note_for_a_medicine_with_an_end():
    row = "Paracetamol 500 mg tablets. Take 2 tablets four times a day for 14 days."
    assert turn.open_ended_medicine_note(marked(row), "How long do I take paracetamol?", STATE) is None


def test_no_note_for_an_only_if_needed_medicine():
    row = "Senna 7.5 mg tablets. Take 2 tablets at bedtime if constipated."
    assert turn.open_ended_medicine_note(marked(row), "How long do I take senna?", STATE) is None


def test_no_note_when_the_question_is_not_about_how_long():
    assert turn.open_ended_medicine_note(marked(APIXABAN_ROW), "When do I take my blood thinner? After breakfast.", STATE) is None


def test_no_note_without_a_source_or_when_no_single_medicine_is_marked():
    assert turn.open_ended_medicine_note(None, QUESTION, STATE) is None
    assert turn.open_ended_medicine_note(marked("Do not kneel on the operated knee."), QUESTION, STATE) is None
    both = marked("Apixaban 2.5 mg tablets and Paracetamol 500 mg tablets.")
    assert turn.open_ended_medicine_note(both, QUESTION, STATE) is None


def test_the_paragraph_printed_after_the_table_is_not_part_of_the_last_row():
    longer = TABLE.replace(
        "Usual medicines before admission: no",
        "Usual medicines before admission: none. All medicines above were given to you by the hospital pharmacy.",
    )
    match = {"text": longer, "page": 1, "document_id": "d", "chunk_id": "c", "distance": 0.3}
    source = select_rag_source(REPLY, [match], context_texts=[QUESTION], entity_names=["Apixaban 2.5 mg tablets"])

    assert source["text"].split("\n")[-1] == "4. Senna 7.5 mg tablets. Take 2 tablets at bedtime if constipated."
    assert "Usual medicines" not in source["text"]
    assert source["highlight"] == APIXABAN_ROW
