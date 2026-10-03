"""Test splitting document text into chunks while preserving useful page information."""

from app.rag.chunking import (
    chunk_document,
)


def test_chunk_document():

    pages = [
        {
            "page": 1,
            "text": (
                "Take Amoxicillin three times daily. "
                "Do not drive for seven days. "
                "Take short walks daily."
            ),
        },
        {
            "page": 2,
            "text": (
                "Call 999 if severe breathlessness "
                "or chest pain develops."
            ),
        },
    ]

    chunks = chunk_document(
        pages,
        document_id="test_doc",
    )

    assert len(chunks) >= 2

    assert (
        chunks[0]["document_id"]
        == "test_doc"
    )

    assert (
        chunks[0]["page"]
        == 1
    )

    assert chunks[0]["text"]