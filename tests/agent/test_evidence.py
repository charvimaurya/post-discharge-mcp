"""Test that the API source is the letter item the reply used."""

from app.agent.evidence import (
    collect_rag_matches,
    select_rag_source,
    split_citation,
    split_letter_items,
)


# Synthetic letter chunks in the shape search_discharge_instructions
# returns, ranked so the nearest chunk is NOT the one quoted.
HEADER_CHUNK = {
    "chunk_id": "doc_p1_c0",
    "document_id": "doc",
    "page": 1,
    "text": (
        "DISCHARGE LETTER\nPatient:\nTest Patient\nMEDICINES TO TAKE AT HOME\n1.\n"
        "Paracetamol 500 mg tablets. Take 2 tablets four times a day.\n2.\n"
        "Codeine 30 mg tablets. Take 1 tablet only if needed for pain."
    ),
}

MEDS_CHUNK = {
    "chunk_id": "doc_p1_c1",
    "document_id": "doc",
    "page": 1,
    "text": (
        "3.\nApixaban 2.5 mg tablets. Take 1 tablet twice a day (morning and evening). "
        "Take the morning dose after\nbreakfast. Continue as directed.\n4.\n"
        "Senna 7.5 mg tablets. Take 2 tablets at bedtime if constipated."
    ),
}

RESTRICTIONS_CHUNK = {
    "chunk_id": "doc_p1_c2",
    "document_id": "doc",
    "page": 1,
    "text": (
        "Your wound clips will be removed on Monday 26 October 2026.\nRESTRICTIONS\n\x7f\n"
        "Do not drive until your consultant has reviewed you at your 6-week appointment "
        "and told you it is safe.\n\x7f\nDo not kneel on the operated knee.\n"
        "FOLLOW-UP APPOINTMENTS\n\x7f\n"
        "Consultant review: Monday 23 November 2026, 9:15 am, Orthopaedic Clinic."
    ),
}

RANKED = [HEADER_CHUNK, MEDS_CHUNK, RESTRICTIONS_CHUNK]


def test_items_split_on_bullets_numbers_and_headings():
    items = split_letter_items(RESTRICTIONS_CHUNK["text"])
    assert (
        "Do not drive until your consultant has reviewed you at your 6-week "
        "appointment and told you it is safe."
    ) in items
    assert "RESTRICTIONS" not in " ".join(items)

    meds = split_letter_items(MEDS_CHUNK["text"])
    # Wrapped lines are re-joined into one item.
    assert meds[0].endswith("Take the morning dose after breakfast. Continue as directed.")


def test_driving_source_is_restriction_not_first_chunk():
    reply = (
        "Your paperwork says do not drive until your consultant has reviewed you at "
        "your 6-week appointment and told you it is safe. That appointment is on "
        "23 November 2026 at 9:15 am."
    )
    source = select_rag_source(reply, RANKED)
    assert source["chunk_id"] == "doc_p1_c2"
    assert source["highlighted_line"].startswith("Do not drive until your consultant")
    assert source["passage"] == RESTRICTIONS_CHUNK["text"]
    assert (source["document_id"], source["page"]) == ("doc", 1)


def test_blood_thinner_source_contains_continue_as_directed():
    reply = (
        "Your paperwork says to take apixaban 2.5 mg tablets, 1 tablet twice a day, "
        "morning and evening, and to continue as directed. It does not state an end "
        "date, so check with your care team."
    )
    source = select_rag_source(reply, RANKED)
    assert source["chunk_id"] == "doc_p1_c1"
    assert "Continue as directed." in source["highlighted_line"]


def test_reply_without_letter_evidence_has_no_source():
    assert select_rag_source("You're welcome. Let me know when you're ready.", RANKED) is None
    assert select_rag_source("Your walk is recorded.", []) is None


def test_only_successful_search_results_are_collected():
    ok = {"ok": True, "data": RANKED}
    assert collect_rag_matches("search_discharge_instructions", ok) == RANKED
    assert collect_rag_matches("get_recovery_plan", ok) == []
    assert collect_rag_matches("search_discharge_instructions", {"ok": False, "data": RANKED}) == []


def test_quoted_letter_text_beats_longer_paraphrase():
    # The reply spells out the appointment but QUOTES the medicine line.
    reply = (
        'Your discharge letter says to take Apixaban "continue as directed", but it '
        "doesn't specify an end date. You have a consultant review on 23 November "
        "2026 at the Orthopaedic Clinic."
    )
    source = select_rag_source(reply, RANKED)
    assert source["chunk_id"] == "doc_p1_c1"
    assert "Continue as directed." in source["highlighted_line"]


def test_curly_quotes_match_across_punctuation():
    reply = "It says “Do not kneel on the operated knee”."
    source = select_rag_source(reply, RANKED)
    assert source["highlighted_line"] == "Do not kneel on the operated knee."


def test_paraphrase_of_long_item_still_gets_source():
    # Regression: the reply uses only the key words of a long
    # medicine line, so plain coverage was too low (source=null).
    reply = (
        "Your paperwork says to take apixaban twice a day and continue as "
        "directed, but it doesn't state a specific end date. Check with your "
        "care team about when to stop."
    )
    source = select_rag_source(reply, RANKED)
    assert source["chunk_id"] == "doc_p1_c1"
    assert "Continue as directed." in source["highlighted_line"]


def test_not_in_letter_reply_has_no_source():
    reply = "Your paperwork doesn't mention flying. Please check with your care team."
    assert select_rag_source(reply, RANKED) is None


QUESTION = ["How long do I take the blood thinner for?", "blood thinner duration how long"]


def test_question_words_complete_a_paraphrase_without_the_drug_name():
    # Regression: the reply says "blood thinner", never the drug name,
    # so it shares only "continue" and "directed" with the letter line.
    reply = (
        "Your paperwork says to continue the blood thinner as directed but "
        "doesn't state when to stop. I'd suggest checking with your care team."
    )
    source = select_rag_source(reply, RANKED, QUESTION)
    assert source["chunk_id"] == "doc_p1_c1"
    assert "Continue as directed." in source["highlighted_line"]


def test_question_alone_cannot_create_a_source():
    # The question matches the medicine line, but the reply uses no evidence.
    reply = "I couldn't find that in your discharge letter. Please check with your care team."
    assert select_rag_source(reply, RANKED, QUESTION) is None



# ---------------------------------------------------------------
# Evidence tag: deterministic source, independent of reply wording
# ---------------------------------------------------------------

def test_split_citation_strips_tag_from_spoken_reply():
    spoken, chunk_id, line = split_citation(
        "The letter says continue as directed. No end date is stated."
        " [[evidence: doc_p1_c1 | Continue as directed.]]"
    )
    assert spoken == "The letter says continue as directed. No end date is stated."
    assert (chunk_id, line) == ("doc_p1_c1", "Continue as directed.")
    assert split_citation("No tag here.") == ("No tag here.", None, None)


def test_valid_tag_with_supporting_line_is_accepted():
    reply = "Your letter says to continue as directed, so no end date is stated."
    source = select_rag_source(
        reply, RANKED, cited_chunk_id="doc_p1_c1", cited_line="Continue as directed.",
    )
    assert source["chunk_id"] == "doc_p1_c1"
    assert source["passage"] == MEDS_CHUNK["text"]
    assert "Continue as directed." in source["highlighted_line"]


def test_tag_alone_cannot_attach_evidence_the_reply_does_not_use():
    # Real chunk + real line, but the reply uses none of it.
    reply = "There's no end date for your blood thinner; ask your care team."
    assert select_rag_source(
        reply, RANKED, cited_chunk_id="doc_p1_c1", cited_line="Continue as directed.",
    ) is None


def test_real_but_unsupporting_tag_is_rejected_and_fallback_finds_support():
    # Regression (Sonnet run): the tag names a real chunk and a line
    # really in it (the Paracetamol entry), but the reply's letter
    # phrase is "continue as directed", which only the Apixaban
    # line contains, in another returned chunk.
    reply = (
        "Your letter says to continue as directed, so the end date isn't "
        "stated. It's best to check with your care team at your next appointment."
    )
    source = select_rag_source(
        reply,
        RANKED,
        context_texts=["How long do I take the blood thinner for?"],
        cited_chunk_id="doc_p1_c0",
        cited_line="Paracetamol 500 mg tablets.",
    )
    assert source["chunk_id"] == "doc_p1_c1"
    assert "Continue as directed." in source["highlighted_line"]
    assert "Paracetamol" not in source["highlighted_line"]


def test_tag_with_line_not_in_chunk_falls_back_to_supporting_item():
    reply = "Do not drive until your consultant has reviewed you and told you it is safe."
    source = select_rag_source(
        reply, RANKED, cited_chunk_id="doc_p1_c2", cited_line="Invented line that is not there.",
    )
    assert source["chunk_id"] == "doc_p1_c2"
    assert source["highlighted_line"].startswith("Do not drive")


def test_driving_tag_with_appointment_second_sentence():
    reply = (
        "Your paperwork says do not drive until your consultant has reviewed you "
        "at your 6-week appointment and told you it is safe. Your consultant "
        "review is on Monday 23 November 2026 at 9:15 am."
    )
    source = select_rag_source(
        reply, RANKED, cited_chunk_id="doc_p1_c2",
        cited_line="Do not drive until your consultant has reviewed you",
    )
    assert source["highlighted_line"].startswith("Do not drive")


def test_named_medication_must_match_the_source():
    # The reply names a grounded medication; a line about another
    # medicine with similar wording must not be chosen.
    reply = "Your letter says to take Senna 7.5 mg tablets at bedtime if constipated."
    source = select_rag_source(
        reply, RANKED, entity_names=["Paracetamol", "Senna", "Apixaban"],
    )
    assert "Senna" in source["highlighted_line"]


def test_unknown_cited_chunk_is_ignored():
    # A chunk_id the search never returned cannot become a source.
    reply = "You're welcome. Let me know when you're ready."
    assert select_rag_source(reply, RANKED, cited_chunk_id="made_up_chunk") is None
    assert select_rag_source(reply, [], cited_chunk_id="doc_p1_c1") is None


def test_paraphrase_first_sentence_beats_appointment_second_sentence():
    # The letter wording is split by other words ("continue the blood
    # thinner as directed"); the second sentence names an appointment.
    reply = (
        "Your discharge letter says to continue the blood thinner as directed, "
        "but doesn't specify an end date. You can ask at your consultant review "
        "on 23 November 2026."
    )
    source = select_rag_source(reply, RANKED)
    assert source["chunk_id"] == "doc_p1_c1"
    assert "Continue as directed." in source["highlighted_line"]
