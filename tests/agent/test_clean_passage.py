"""The letter panel's excerpt: whole sentences, one block, the answering sentence marked."""

import re

from app.agent.evidence import clean_passage, select_rag_source


CHUNK = (
    "akfast.\n2.\nCodeine 30 mg tablets. Take 1 tablet up to four times a day, only if needed for pain. "
    "Stop after 5 days.\n3.\nApixaban 2.5 mg tablets. Take 1 tablet twice a day (morning and evening). "
    "Take the morning dose after\nbreakfast. Continue as directed.\n4.\nSenna 7.5 mg tablets. "
    "Take 2 tablets at bedtime if constipated.\nDAILY ACTIVITIES\n\nKnee exercises ...\n\nYour wound clip"
)

RESTRICTIONS = (
    "Your wound clips will be removed on Monday 26 October 2026.\nRESTRICTIONS\n\x7f\n"
    "Do not drive until your consultant has reviewed you at your 6-week appointment "
    "and told you it is safe.\n\x7f\nDo not kneel on the operated knee.\n"
    "FOLLOW-UP APPOINTMENTS\n\x7f\n"
    "Consultant review: Monday 23 November 2026, 9:15 am, Orthopaedic Clinic."
)

BLOOD_THINNER = "When do I take my blood thinner? Your letter says to take the morning dose after breakfast."


def test_blood_thinner_excerpt_is_the_apixaban_item():
    excerpt = clean_passage(CHUNK, BLOOD_THINNER)

    assert excerpt["text"].startswith("3. Apixaban")
    # The cut-off "akfast." fragment is gone ("breakfast" itself contains those letters).
    assert not re.search(r"\bakfast\b", excerpt["text"])
    assert "Your wound clip" not in excerpt["text"]
    assert "\n" not in excerpt["text"]
    assert excerpt["highlight"] == "Take the morning dose after breakfast."
    assert excerpt["highlight"] in excerpt["text"]


def test_wording_is_unchanged_apart_from_whitespace():
    excerpt = clean_passage(CHUNK, BLOOD_THINNER)

    assert excerpt["text"] == (
        "3. Apixaban 2.5 mg tablets. Take 1 tablet twice a day (morning and evening). "
        "Take the morning dose after breakfast. Continue as directed."
    )


def test_no_line_break_inside_a_sentence():
    excerpt = clean_passage(CHUNK, BLOOD_THINNER)

    assert "after breakfast" in excerpt["text"]


def test_bullet_becomes_a_dash_and_section_is_the_heading_above():
    excerpt = clean_passage(RESTRICTIONS, "Your letter says do not drive until your consultant has reviewed you.")

    assert excerpt["section"] == "Restrictions"
    assert excerpt["text"] == (
        "- Do not drive until your consultant has reviewed you at your 6-week appointment "
        "and told you it is safe."
    )
    assert excerpt["highlight"].startswith("Do not drive")
    assert "\x7f" not in excerpt["text"]


def test_section_is_none_when_no_heading_is_above():
    assert clean_passage(CHUNK, BLOOD_THINNER)["section"] is None


def test_nothing_matching_gives_no_excerpt():
    assert clean_passage(CHUNK, "What colour is the sky?") is None


def test_long_paragraph_is_cut_to_three_sentences_in_a_row():
    text = "One a. Two b. Three c. Four driving rule. Five e. Six f."
    excerpt = clean_passage(text, "driving rule")

    assert excerpt["text"] == "Three c. Four driving rule. Five e."
    assert excerpt["highlight"] == "Four driving rule."


def test_api_source_carries_the_clean_excerpt_and_the_old_fields():
    chunk = {"chunk_id": "doc_p1_c1", "document_id": "doc", "page": 1, "text": CHUNK}
    reply = "Your letter says to take the morning dose after breakfast. Continue as directed."

    source = select_rag_source(reply, [chunk], ["When do I take my blood thinner?"])

    assert source["page"] == 1
    assert source["text"].startswith("3. Apixaban")
    assert source["highlight"] == "Take the morning dose after breakfast."
    assert source["section"] is None
    # Older readers still get the raw chunk and the matched item.
    assert source["passage"] == CHUNK
    assert "Continue as directed." in source["highlighted_line"]
