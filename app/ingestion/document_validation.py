"""Reject unrelated documents before extraction creates a recovery plan."""

import re


WRONG_DOCUMENT_MESSAGE = (
    "Wrong document — not accepted. Please upload a hospital discharge letter."
)


class WrongDocumentError(ValueError):
    def __init__(self):
        super().__init__(WRONG_DOCUMENT_MESSAGE)


# Require discharge context and care content, rather than just the word
# "hospital" (which is also found on invoices, CVs and appointment letters).
_DISCHARGE = re.compile(
    r"\b(?:discharge (?:letter|summary|instructions|advice|information|plan|date|medications?|medicines?)|"
    r"date of discharge|discharged (?:home|on|from)|leaving hospital|going home from hospital)\b"
)
_CARE = re.compile(
    r"\b(?:medications?|medicines?|tablets?|diagnosis|procedure|operation|surgery|"
    r"treatment|wound|dressing|recovery|restrictions?|follow up|appointments?|"
    r"warning signs|symptoms|physiotherapy|exercises?|care plan|care team)\b"
)


def validate_discharge_document(text: str) -> None:
    """Require readable discharge context plus clinical care content.

    This is a document-type check, not verification of identity or authenticity.
    Empty/scanned PDFs cannot establish document type and are rejected too.
    """
    words = " ".join(re.findall(r"[a-z0-9]+", (text or "").lower()))
    if not _DISCHARGE.search(words) or not _CARE.search(words):
        raise WrongDocumentError()
