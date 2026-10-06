"""
Utilities for splitting discharge-document pages into
small pieces suitable for semantic retrieval.

Important:

We preserve the page number because RAG results should be
traceable back to the original discharge paperwork.
"""


def _split_text(
    text: str,
    *,
    chunk_size: int = 800,
    overlap: int = 120,
) -> list[str]:
    """
    Split text into overlapping character chunks.

    Example:

        characters 0-800
        characters 680-1480
        characters 1360-2160

    The overlap helps prevent useful information near a
    chunk boundary from being lost.
    """

    text = text.strip()

    if not text:
        return []

    if overlap >= chunk_size:
        raise ValueError(
            "overlap must be smaller than chunk_size"
        )

    chunks = []

    start = 0

    while start < len(text):

        end = min(
            start + chunk_size,
            len(text),
        )

        piece = text[
            start:end
        ].strip()

        if piece:
            chunks.append(
                piece
            )

        if end >= len(text):
            break

        start = end - overlap

    return chunks


def chunk_document(
    pages: list[dict],
    *,
    document_id: str,
) -> list[dict]:
    """
    Convert extracted document pages into retrieval chunks.

    Expected page format:

        {
            "page": 1,
            "text": "..."
        }

    Returns:

        [
            {
                "chunk_id": "document_p1_c0",
                "document_id": "...",
                "page": 1,
                "section": "page_1",
                "text": "..."
            }
        ]
    """

    chunks = []

    for page_data in pages:

        page_number = (
            page_data.get("page")
            or page_data.get("page_number")
        )

        text = page_data.get(
            "text",
            "",
        )

        if page_number is None:
            raise ValueError(
                "Page is missing page number"
            )

        page_chunks = _split_text(
            text,
        )

        for index, piece in enumerate(
            page_chunks
        ):

            chunk_id = (
                f"{document_id}"
                f"_p{page_number}"
                f"_c{index}"
            )

            chunks.append(
                {
                    "chunk_id":
                        chunk_id,

                    "document_id":
                        document_id,

                    "page":
                        int(page_number),

                    "section":
                        f"page_{page_number}",

                    "text":
                        piece,
                }
            )

    return chunks