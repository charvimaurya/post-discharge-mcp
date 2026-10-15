"""The letter's own emergency number, and permission questions that speech recognition garbles."""

import pytest

from app.agent.safety import is_permission_question, says_not_in_letter
from app.agent.symptoms import emergency_number, find_symptom, help_actions, no_match_reply, warning_sign_reply

# Margaret's letter, page 2, as indexed.
PAGE_2 = (
    "Call emergency services straight away if you have chest pain or sudden shortness of breath.\n"
    "Emergency services number: 555-555-0199 (fictional number)\n"
    "INFORMATION FOR YOUR GP"
)
EMERGENCY = {"id": "w5", "urgency": "emergency", "action": "Call emergency services straight away",
             "text": "chest pain or sudden shortness of breath",
             "source": {"snippet": "Call emergency services straight away if you have chest pain or sudden shortness of breath."}}
WARD = {"id": "w1", "urgency": "contact_care_team", "action": "Call the ward on 0000 000 000 (fictional number)",
        "text": "Pain, swelling, redness or heat in your calf"}


@pytest.mark.parametrize("text, number", [
    (PAGE_2, "555-555-0199"),
    ("Emergency number: 112", "112"),
    ("In an emergency phone line - +44 (0)20 7946 0000", "+44 (0)20 7946 0000"),
    ("Call the ward on 0000 000 000 (fictional number)", None),
    ("Switchboard: 0000 000 000 · Ward: 0000 000 001", None),
])
def test_the_emergency_number_is_read_from_the_letter(text, number):
    assert emergency_number(["unrelated", text]) == number


def test_the_emergency_sign_reply_says_the_letters_number():
    reply = warning_sign_reply(EMERGENCY, "Margaret", "555-555-0199")

    assert reply == (
        "I'm sorry to hear that, Margaret. Your letter says: Call emergency services straight away "
        "if you have chest pain or sudden shortness of breath. The emergency number in your letter is 555-555-0199."
    )
    # Not for a sign that says to call the ward.
    assert "555" not in warning_sign_reply(WARD, "Margaret", "555-555-0199")
    # No number in the letter: the reply is as before.
    assert "emergency number" not in warning_sign_reply(EMERGENCY, "Margaret", None)


def test_the_fixed_reply_uses_the_letters_number_instead_of_999():
    symptom = find_symptom("my head hurts")

    assert "call 555-555-0199" in no_match_reply(symptom, "Margaret", "555-555-0199")
    assert "999" not in no_match_reply(symptom, "Margaret", "555-555-0199")
    assert "call 999" in no_match_reply(symptom, "Margaret", None)


def test_the_help_card_gets_the_number_on_the_emergency_action():
    actions = help_actions([WARD, EMERGENCY], "555-555-0199")

    assert actions[0] == {"urgency": "emergency", "action": "Call emergency services straight away: 555-555-0199"}
    assert actions[1]["action"] == "Call the ward on 0000 000 000 (fictional number)"
    assert help_actions([WARD, EMERGENCY])[0]["action"] == "Call emergency services straight away"


@pytest.mark.parametrize("message", [
    "Alexa can a plan to go for drive",
    "Alexa, can I plan to go for a drive?",
    "Alexa I plan to go for a drive",
    "is driving ok",
    "can we go swimming",
])
def test_permission_questions_even_when_misheard(message):
    assert is_permission_question(message)


@pytest.mark.parametrize("message", ["I took my tablets", "what's next?", "I had my breakfast"])
def test_reports_are_not_permission_questions(message):
    assert not is_permission_question(message)


def test_saying_the_letter_does_not_cover_it():
    assert says_not_in_letter("I don't have information about driving in your recovery plan.")
    assert says_not_in_letter("Your letter doesn't mention swimming.")
    assert not says_not_in_letter("Your letter says you should not drive until your consultant has reviewed you.")


def test_the_letters_emergency_line_is_shown_as_its_own_card():
    from app.agent.symptoms import emergency_contact, sign_source, with_emergency_line

    contact = emergency_contact([("no number here", 1), ("\x7f " + PAGE_2, 2)])
    assert contact == {"number": "555-555-0199",
                       "line": "Emergency services number: 555-555-0199 (fictional number)", "page": 2}

    source = with_emergency_line(sign_source(EMERGENCY), contact)
    assert source["section"] == "Warning signs"
    assert source["related"] == [{"text": "Emergency services number: 555-555-0199 (fictional number)",
                                  "page": 2, "label": "Emergency number"}]

    # The letter says nothing about the symptom: its emergency line is what the panel shows.
    alone = with_emergency_line(None, contact)
    assert alone["section"] == "Emergency number" and alone["highlight"].endswith("(fictional number)")

    # No number in the letter: nothing is added.
    assert with_emergency_line(sign_source(EMERGENCY), None) == sign_source(EMERGENCY)
