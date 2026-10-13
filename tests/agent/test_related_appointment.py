"""A passage that points at an appointment is shown with that appointment's own line from the letter."""

from decimal import Decimal

from app.agent.evidence import related_appointment_lines


DRIVING = "Do not drive until your consultant has reviewed you at your 6-week appointment and told you it is safe."
CONSULTANT_LINE = "Consultant review: Monday 23 November 2026, 9:15 am, Orthopaedic Clinic, Example General Hospital."

APPOINTMENTS = [
    {"title": "Physiotherapy", "source": {"page": Decimal(2), "snippet": "Physiotherapy: Thursday 22 October 2026, 2:00 pm."}},
    {"title": "Wound clip removal", "source": {"page": Decimal(2), "snippet": "Wound clip removal: Monday 26 October 2026, 10:30 am."}},
    {"title": "Consultant review", "source": {"page": Decimal(2), "snippet": CONSULTANT_LINE}},
]

# What the panel's "linked appointment" card shows.
CONSULTANT = {"text": CONSULTANT_LINE, "page": 2}


def source(highlight, text=None):
    return {"page": 1, "section": "Restrictions", "text": text or highlight, "highlight": highlight}


def test_driving_restriction_brings_the_consultant_review_line():
    assert related_appointment_lines(source(DRIVING), APPOINTMENTS) == [CONSULTANT]


def test_page_is_a_plain_number_so_the_reply_can_be_sent_as_json():
    (line,) = related_appointment_lines(source(DRIVING), APPOINTMENTS)
    assert type(line["page"]) is int


def test_a_passage_that_names_no_appointment_brings_nothing():
    assert related_appointment_lines(source("Do not kneel on the operated knee."), APPOINTMENTS) == []
    # "physiotherapy" appears, but the sentence is about exercises, not an appointment.
    assert related_appointment_lines(source("Knee exercises from your physiotherapy sheet: three times a day."), APPOINTMENTS) == []


def test_an_appointment_the_passage_does_not_name_is_not_guessed():
    only_others = APPOINTMENTS[:2]
    assert related_appointment_lines(source(DRIVING), only_others) == []


def test_nothing_is_added_when_the_letter_has_no_line_for_it():
    without_wording = [{"title": "Consultant review", "source": {"page": 2, "snippet": ""}}, {"title": "Consultant review"}]
    assert related_appointment_lines(source(DRIVING), without_wording) == []


def test_a_line_already_in_the_passage_is_not_repeated():
    passage = f"{DRIVING}\n{CONSULTANT_LINE}"
    assert related_appointment_lines(source(DRIVING, passage), APPOINTMENTS) == []


def test_no_source_or_no_appointments_brings_nothing():
    assert related_appointment_lines(None, APPOINTMENTS) == []
    assert related_appointment_lines(source(DRIVING), None) == []
    assert related_appointment_lines(source(DRIVING), []) == []


def test_older_source_fields_are_read_too():
    older = {"page": 1, "passage": f"What you must not do\n{DRIVING}", "highlighted_line": DRIVING}
    assert related_appointment_lines(older, APPOINTMENTS) == [CONSULTANT]


def test_a_line_only_in_the_raw_chunk_is_still_shown():
    # The retrieved chunk can run on into the appointments section, but the panel shows
    # only the excerpt, so the appointment line must still be added.
    raw_chunk = "\n".join(["RESTRICTIONS", DRIVING, "FOLLOW-UP APPOINTMENTS", CONSULTANT_LINE])
    with_raw_chunk = dict(source(DRIVING), passage=raw_chunk)
    assert related_appointment_lines(with_raw_chunk, APPOINTMENTS) == [CONSULTANT]
