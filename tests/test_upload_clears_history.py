"""A newly uploaded discharge letter deletes what was recorded against the previous one."""

import pytest
from tests.bridge_client import BridgeClient as TestClient

from app import web_bridge
from app.database import event_history
from app.mcp.context import get_demo_patient_context


class FakeBatch:
    def __init__(self, deleted):
        self.deleted = deleted

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def delete_item(self, Key):
        self.deleted.append(Key)


class FakeTable:
    """Event rows for several patients; one patient's rows are returned two per query page."""

    def __init__(self, rows, patient_id):
        self.rows = rows
        self.patient_id = patient_id
        self.deleted = []
        self.queries = 0

    def batch_writer(self):
        return FakeBatch(self.deleted)

    def query(self, **kwargs):
        self.queries += 1
        patient_rows = [row for row in self.rows if row["patient_id"] == self.patient_id]
        start = kwargs.get("ExclusiveStartKey", 0)
        response = {"Items": patient_rows[start:start + 2]}

        if start + 2 < len(patient_rows):
            response["LastEvaluatedKey"] = start + 2

        return response


def rows(patient_id, count):
    return [{"patient_id": patient_id, "timestamp": f"event#{patient_id}-{n}"} for n in range(count)]


def test_delete_events_removes_every_page_for_that_patient_only(monkeypatch):
    table = FakeTable(rows("patient_a", 5) + rows("patient_b", 3), "patient_a")
    monkeypatch.setattr(event_history, "event_table", table)

    assert event_history.delete_events("patient_a") == 5

    assert table.queries == 3
    assert [key["timestamp"] for key in table.deleted] == [f"event#patient_a-{n}" for n in range(5)]
    assert all(key["patient_id"] == "patient_a" for key in table.deleted)


def test_delete_events_with_nothing_recorded_deletes_nothing(monkeypatch):
    table = FakeTable([], "patient_a")
    monkeypatch.setattr(event_history, "event_table", table)

    assert event_history.delete_events("patient_a") == 0
    assert table.deleted == []


@pytest.mark.parametrize("patient_id", ["", "   "])
def test_delete_events_refuses_an_empty_patient(patient_id):
    with pytest.raises(ValueError):
        event_history.delete_events(patient_id)


def test_bridge_clears_the_server_side_patient_and_ignores_the_body(monkeypatch):
    cleared = []
    monkeypatch.setattr(web_bridge, "delete_events", lambda patient_id: cleared.append(patient_id) or 7)

    response = TestClient(web_bridge.app).post("/documents/uploaded", json={"patient_id": "someone_else"})

    assert response.status_code == 200
    assert response.json() == {"deleted": 7}
    assert cleared == [get_demo_patient_context().patient_id]


def test_bridge_reports_a_failed_clear_without_details(monkeypatch):
    def broken(patient_id):
        raise RuntimeError("table name and key details")

    monkeypatch.setattr(web_bridge, "delete_events", broken)

    response = TestClient(web_bridge.app).post("/documents/uploaded")

    assert response.status_code == 502
    assert response.json() == {"error": web_bridge.HISTORY_ERROR}


def test_bridge_clear_is_post_only():
    assert TestClient(web_bridge.app).get("/documents/uploaded").status_code == 405
