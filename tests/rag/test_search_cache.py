"""Letter searches and query embeddings are cached per letter, and never across letters."""

import pytest

from app.rag import service


@pytest.fixture
def aws(monkeypatch):
    """Fakes for the record read, the embedding call and the vector query, with call counts."""

    calls = {"state": 0, "embed": 0, "query": 0}
    current = {"document_id": "doc_1", "matches": True}

    def get_state(patient_id):
        calls["state"] += 1
        return {"document_id": current["document_id"]}

    def embed(text):
        calls["embed"] += 1
        return [0.1] * 4

    def query(*, query_embedding, patient_id, document_id, top_k):
        calls["query"] += 1
        if not current["matches"]:
            return []
        return [{"key": f"{document_id}#c1", "distance": 0.2,
                 "metadata": {"document_id": document_id, "page": 1, "section": "RESTRICTIONS", "text": "Do not drive."}}]

    monkeypatch.setattr(service, "get_recovery_state", get_state)
    monkeypatch.setattr(service, "embed_text", embed)
    monkeypatch.setattr(service, "query_chunks", query)
    return calls, current


def search(text="Can I drive?"):
    return service.search_discharge_instructions(query=text, patient_id="patient_a")


def test_the_same_question_is_searched_once(aws):
    calls, _ = aws

    first = search()
    second = search()

    assert first == second
    assert (calls["embed"], calls["query"]) == (1, 1)


def test_the_current_letter_is_still_read_every_time(aws):
    calls, _ = aws

    search()
    search()

    assert calls["state"] == 2


def test_a_new_letter_is_searched_afresh(aws):
    calls, current = aws

    search()
    current["document_id"] = "doc_2"
    result = search()

    assert calls["query"] == 2
    assert result[0]["document_id"] == "doc_2"
    # The question's embedding does not depend on the letter, so it is reused.
    assert calls["embed"] == 1


def test_spacing_and_capitals_do_not_make_a_new_search(aws):
    calls, _ = aws

    search("Can I drive?")
    search("  can i   DRIVE? ")

    assert calls["query"] == 1


def test_an_empty_result_is_not_kept(aws):
    calls, current = aws
    current["matches"] = False

    assert search() == []
    current["matches"] = True
    assert search() != []
    assert calls["query"] == 2


def test_changing_a_returned_result_does_not_change_the_cache(aws):
    first = search()
    first[0]["text"] = "changed"

    assert search()[0]["text"] == "Do not drive."


def test_the_cache_is_bounded(aws, monkeypatch):
    monkeypatch.setattr(service, "MAX_CACHED_SEARCHES", 3)

    for n in range(5):
        search(f"question {n}")

    assert len(service._search_cache) == 3
    assert len(service._embedding_cache) == 3
