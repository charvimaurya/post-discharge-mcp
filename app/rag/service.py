"""Coordinate document indexing and patient-filtered retrieval of original discharge evidence.

This module coordinates:
- chunking
- embeddings
- S3 Vectors indexing
- retrieval
"""

from app.database.recovery_state import (
    get_recovery_state,
)

from app.rag.chunking import (
    chunk_document,
)

from app.rag.embeddings import (
    embed_text,
)

from app.rag.vector_store import (
    put_chunks,
    query_chunks,
)


def index_document_pages(
    *,
    patient_id: str,
    document_id: str,
    pages: list[dict],
) -> int:
    """
    Chunk, embed and store one patient's discharge
    document.

    Returns number of vectors indexed.
    """

    chunks = chunk_document(
        pages,
        document_id=document_id,
    )

    embeddings = []

    for chunk in chunks:

        embedding = embed_text(
            chunk["text"]
        )

        embeddings.append(
            embedding
        )

    put_chunks(
        patient_id=patient_id,
        document_id=document_id,
        chunks=chunks,
        embeddings=embeddings,
    )

    return len(chunks)


def search_discharge_instructions(
    *,
    query: str,
    patient_id: str,
    top_k: int = 5,
) -> list[dict]:
    """
    Return discharge evidence from the authenticated
    patient's CURRENT recovery-plan document only.

    RecoveryState tells us which document is currently
    authoritative for this patient.
    """

    if not isinstance(patient_id, str) or not patient_id.strip():
        raise ValueError(
            "patient_id must be a non-empty string"
        )

    # -------------------------------------------------
    # 1. LOAD CURRENT RECOVERY STATE
    # -------------------------------------------------
    #
    # A patient may have older documents in the vector
    # index. RecoveryState tells us which document is the
    # current authoritative one.
    #
    state = get_recovery_state(
        patient_id
    )

    if not state:
        return []

    document_id = state.get(
        "document_id"
    )

    if not document_id:
        return []

    # -------------------------------------------------
    # 2. SEARCH ONLY THAT DOCUMENT
    # -------------------------------------------------
    query_embedding = embed_text(query)
    matches = query_chunks(
        query_embedding=query_embedding,
        patient_id=patient_id,
        document_id=document_id,
        top_k=top_k,
    )

    results = []
    for match in matches:
        metadata = match.get("metadata", {})
        results.append(
            {
                "chunk_id": match.get("key"),
                "distance": match.get("distance"),
                "document_id": metadata.get("document_id"),
                "page": metadata.get("page"),
                "section": metadata.get("section"),
                "text": metadata.get("text"),
            }
        )
    return results
