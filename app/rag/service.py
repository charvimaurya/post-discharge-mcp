"""Coordinate document indexing and patient-filtered retrieval of original discharge evidence.

This module coordinates:
- chunking
- embeddings
- S3 Vectors indexing
- retrieval
"""

import threading
from collections import OrderedDict

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


# ---------------------------------------------------------
# Search caches
# ---------------------------------------------------------
#
# The same questions come up again and again ("Can I drive?"), and the
# answer for one letter never changes: a new upload is a new document_id.
# So a query's embedding, and the matches for (patient, document, query),
# are kept in memory. The current document_id is still read on every
# search, so an old letter's matches are never returned for a new one.
# Empty results are not kept: the letter may still be being indexed.

MAX_CACHED_SEARCHES = 256

_cache_lock = threading.Lock()
_embedding_cache: "OrderedDict[str, list[float]]" = OrderedDict()
_search_cache: "OrderedDict[tuple, list[dict]]" = OrderedDict()


def _remember(cache: OrderedDict, key, value) -> None:
    with _cache_lock:
        cache[key] = value
        cache.move_to_end(key)
        while len(cache) > MAX_CACHED_SEARCHES:
            cache.popitem(last=False)


def _recall(cache: OrderedDict, key):
    with _cache_lock:
        if key not in cache:
            return None
        cache.move_to_end(key)
        return cache[key]


def _query_embedding(query: str) -> list[float]:
    """The query's embedding, computed once per distinct question text."""

    key = " ".join(query.split())
    cached = _recall(_embedding_cache, key)

    if cached is None:
        cached = embed_text(key)
        _remember(_embedding_cache, key, cached)

    return cached


def clear_search_caches() -> None:
    with _cache_lock:
        _embedding_cache.clear()
        _search_cache.clear()


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
    cache_key = (patient_id, document_id, " ".join(query.split()).lower(), top_k)
    cached = _recall(_search_cache, cache_key)

    if cached is not None:
        # Copies, so a caller changing a result never changes the cache.
        return [dict(result) for result in cached]

    query_embedding = _query_embedding(query)
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

    if results:
        _remember(_search_cache, cache_key, [dict(result) for result in results])

    return results
