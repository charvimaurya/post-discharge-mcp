"""Phase 5 checks: use -m 'not integration' for offline tests.

Tests marked integration use the configured AWS tables and complete the first
medication/task on demo_patient_001. They do not reset existing completion state.
"""

from importlib import import_module
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError
import pytest

from app.models.recovery_model import RecoveryState


@pytest.fixture
def event_writer():
    with patch("boto3.resource"):
        module = import_module("app.database.event_history")
    table = Mock()
    with patch.object(module, "event_table", table):
        yield module.append_event, table


def test_retry_reports_duplicate_without_overwriting(event_writer):
    append_event, table = event_writer
    original = append_event("patient", "medication_taken", {"dose": "first"}, "dose-1")
    table.put_item.side_effect = ClientError(
        {"Error": {"Code": "ConditionalCheckFailedException", "Message": "Exists"}},
        "PutItem",
    )

    retry = append_event("patient", "medication_taken", {"dose": "retry"}, "dose-1")

    assert original["created"] is True
    assert original["duplicate"] is False
    assert original["event"] == table.put_item.call_args_list[0].kwargs["Item"]
    assert original["event"]["details"] == {"dose": "first"}
    assert original["event"]["recorded_at"]
    assert "created_at" not in original["event"]
    assert retry == {"created": False, "duplicate": True, "event": None}
    for call in table.put_item.call_args_list:
        assert call.kwargs["Item"]["timestamp"] == original["event"]["timestamp"]
        assert call.kwargs["ConditionExpression"] == (
            "attribute_not_exists(patient_id) AND attribute_not_exists(#ts)"
        )
        assert call.kwargs["ExpressionAttributeNames"] == {
            "#ts": "timestamp",
        }
    table.get_item.assert_not_called()


def test_distinct_occurrences_and_patients_have_distinct_keys(event_writer):
    append_event, _ = event_writer
    first = append_event("patient-1", "medication_taken", {}, "dose-1")["event"]
    second = append_event("patient-1", "medication_taken", {}, "dose-2")["event"]
    other_patient = append_event("patient-2", "medication_taken", {}, "dose-1")["event"]
    keys = {(item["patient_id"], item["timestamp"]) for item in (first, second, other_patient)}
    assert len(keys) == 3
    assert first["idempotency_key"] == "dose-1"
    assert first["timestamp"].startswith("event#")
    assert first["recorded_at"]


@pytest.mark.parametrize("key", ["", "   "])
def test_empty_idempotency_key_is_rejected(event_writer, key):
    append_event, table = event_writer
    with pytest.raises(ValueError, match="idempotency_key"):
        append_event("patient", "event", {}, key)
    table.put_item.assert_not_called()


def test_other_database_errors_are_not_treated_as_duplicates(event_writer):
    append_event, table = event_writer
    error = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "Denied"}}, "PutItem"
    )
    table.put_item.side_effect = error
    with pytest.raises(ClientError) as caught:
        append_event("patient", "event", {}, "key")
    assert caught.value is error
    table.get_item.assert_not_called()


def test_duplicate_does_not_require_reading_existing_event(event_writer):
    append_event, table = event_writer
    table.put_item.side_effect = ClientError(
        {"Error": {"Code": "ConditionalCheckFailedException", "Message": "Exists"}},
        "PutItem",
    )
    result = append_event("patient", "event", {}, "key")
    assert result == {"created": False, "duplicate": True, "event": None}
    table.get_item.assert_not_called()


@pytest.fixture
def key_builder(event_writer):
    # event_writer imports the module with boto3.resource mocked.
    return import_module("app.database.event_history").build_idempotency_key


@pytest.mark.parametrize("item_id", ["med_606698747d", "task_dc63d5eb6c"])
def test_idempotency_key_exact_format(key_builder, item_id):
    assert key_builder("demo_patient_001", item_id, "2026-09-27") == (
        f"demo_patient_001#{item_id}#2026-09-27"
    )


def test_idempotency_key_is_stable(key_builder):
    args = ("demo_patient_001", "med_606698747d", "2026-09-27")
    assert key_builder(*args) == key_builder(*args)


@pytest.mark.parametrize("occurrence", ["2026-09-28", "2026-09-27T08:00"])
def test_idempotency_key_changes_with_occurrence(key_builder, occurrence):
    original = key_builder("demo_patient_001", "med_606698747d", "2026-09-27")
    changed = key_builder("demo_patient_001", "med_606698747d", occurrence)
    assert changed != original
    assert changed == f"demo_patient_001#med_606698747d#{occurrence}"


def test_idempotency_key_changes_with_item(key_builder):
    assert key_builder("demo_patient_001", "med_606698747d", "2026-09-27") != (
        key_builder("demo_patient_001", "task_dc63d5eb6c", "2026-09-27")
    )


def test_idempotency_key_changes_with_patient(key_builder):
    assert key_builder("demo_patient_001", "med_606698747d", "2026-09-27") != (
        key_builder("demo_patient_002", "med_606698747d", "2026-09-27")
    )




@pytest.fixture
def service():
    with patch("boto3.resource"):
        return import_module("app.database.recovery_state")


def test_task_completion_saves_then_records_history(service):
    task = {"id": "task1", "description": "Walk", "status": "pending"}
    state = {"patient_id": "patient", "tasks": [task]}
    calls = Mock()
    event = {"created": True, "duplicate": False, "event": {"event_type": "task_completed"}}
    calls.event.return_value = event
    with patch.object(service, "get_recovery_state", return_value=state), patch.object(service, "save_recovery_state", calls.save), patch.object(service, "append_event", calls.event):
        result = service.mark_task_completed("patient", "task1", "2026-09-30")
    assert result == {"success": True, "already_completed": False, "task": task, "event": event}
    assert task["status"] == "completed"
    assert task["completed_at"] == state["last_updated"]
    assert task["completed_at"].endswith("+00:00")
    assert [call[0] for call in calls.mock_calls] == ["save", "event"]
    calls.save.assert_called_once_with(state)
    calls.event.assert_called_once_with(
        patient_id="patient", event_type="task_completed",
        details={"task_id": "task1", "description": "Walk", "old_status": "pending",
                 "new_status": "completed", "completed_at": task["completed_at"]},
        idempotency_key="patient#task1#2026-09-30",
    )


def test_completed_task_does_not_write_again(service):
    task = {"id": "task1", "status": "completed", "completed_at": "original"}
    with patch.object(service, "get_recovery_state", return_value={"tasks": [task]}), patch.object(service, "save_recovery_state") as save, patch.object(service, "append_event") as event:
        result = service.mark_task_completed("patient", "task1", "same-occurrence")
        assert result["already_completed"] is True
        assert result["event"] is None
        assert task["completed_at"] == "original"
        save.assert_not_called()
        event.assert_not_called()


@pytest.mark.parametrize("state,message", [(None, "Recovery state not found"), ({"tasks": []}, "Task not found")])
def test_missing_state_or_task_does_not_write(service, state, message):
    with patch.object(service, "get_recovery_state", return_value=state), patch.object(service, "save_recovery_state") as save, patch.object(service, "append_event") as event:
        with pytest.raises(ValueError, match=message):
            service.mark_task_completed("patient", "task1")
        save.assert_not_called()
        event.assert_not_called()


def test_save_accepts_dataclass_and_loaded_dictionary(service):
    with patch.object(service, "table") as table:
        service.save_recovery_state(RecoveryState("patient", "document"))
        item = table.put_item.call_args.kwargs["Item"]
        assert item["patient_id"] == "patient"
        service.save_recovery_state(item)
        table.put_item.assert_called_with(Item=item)


PATIENT_ID = "demo_patient_001"


@pytest.mark.parametrize("method,field", [
    ("get_medications", "medications"), ("get_today_tasks", "tasks"),
])
@pytest.mark.parametrize("present", [True, False])
def test_current_list_readers(service, method, field, present):
    items = [{"id": "item1"}]
    state = {field: items} if present else None
    with patch.object(service, "get_recovery_state", return_value=state):
        reader = getattr(service, method)
        assert reader(PATIENT_ID) == (items if present else [])
        assert reader(PATIENT_ID, date="2026-09-30") == (items if present else [])
    with patch.object(service, "get_recovery_state", return_value={"patient_id": PATIENT_ID}):
        assert reader(PATIENT_ID) == []


def test_state_reader_returns_item_or_none(service):
    with patch.object(service, "table") as table:
        table.get_item.return_value = {"Item": {"patient_id": PATIENT_ID}}
        assert service.get_recovery_state(PATIENT_ID) == {"patient_id": PATIENT_ID}
        table.get_item.assert_called_once_with(Key={"patient_id": PATIENT_ID})
        table.get_item.return_value = {}
        assert service.get_recovery_state(PATIENT_ID) is None


def test_event_reader(event_writer):
    from boto3.dynamodb.conditions import Key
    module = import_module("app.database.event_history")
    _, table = event_writer
    items = [{"patient_id": PATIENT_ID, "event_type": "task_completed"}]
    table.query.return_value = {"Items": items}
    assert module.get_events(PATIENT_ID) == items
    table.query.assert_called_once_with(KeyConditionExpression=Key("patient_id").eq(PATIENT_ID))
    table.query.return_value = {}
    assert module.get_events(PATIENT_ID) == []


@pytest.mark.parametrize("action,collection,item_id,result_key,event_type", [
    ("mark_medication_taken", "medications", "med1", "medication", "medication_taken"),
    ("mark_task_completed", "tasks", "task1", "task", "task_completed"),
])
def test_complete_and_repeat_with_explicit_key(service, action, collection, item_id, result_key, event_type):
    from copy import deepcopy
    state = {"patient_id": PATIENT_ID, collection: [
        {"id": item_id, "name": "Amoxicillin", "description": "Walk", "status": "pending"},
    ]}
    calls = Mock()
    calls.event.return_value = {"created": True, "duplicate": False, "event": {"event_type": event_type}}

    def save(updated):
        state.clear()
        state.update(deepcopy(updated))

    calls.save.side_effect = save
    key = f"phase5-test-{item_id}-001"
    with patch.object(service, "get_recovery_state", side_effect=lambda patient: deepcopy(state)), patch.object(service, "save_recovery_state", calls.save), patch.object(service, "append_event", calls.event):
        method = getattr(service, action)
        result = method(PATIENT_ID, item_id, idempotency_key=key)
        assert result["success"] is True
        assert result["already_completed"] is False
        assert result[result_key]["status"] == "completed"
        assert state[collection][0]["completed_at"] == state["last_updated"]
        assert [call[0] for call in calls.mock_calls] == ["save", "event"]
        event_args = calls.event.call_args.kwargs
        assert event_args["idempotency_key"] == key
        assert event_args["event_type"] == event_type
        assert event_args["details"]["old_status"] == "pending"
        assert event_args["details"]["new_status"] == "completed"
        repeat = method(PATIENT_ID, item_id, idempotency_key=key)
        assert repeat["already_completed"] is True
        assert repeat["event"] is None
        calls.save.assert_called_once()
        calls.event.assert_called_once()


@pytest.mark.parametrize("state,message", [
    (None, "No RecoveryState found"), ({"medications": []}, "Medication not found"),
])
def test_missing_medication_or_state(service, state, message):
    with patch.object(service, "get_recovery_state", return_value=state), patch.object(service, "save_recovery_state") as save, patch.object(service, "append_event") as event:
        with pytest.raises(ValueError, match=message):
            service.mark_medication_taken(PATIENT_ID, "missing", "key")
        save.assert_not_called()
        event.assert_not_called()


@pytest.mark.parametrize("method", ["mark_medication_taken", "mark_task_completed"])
@pytest.mark.parametrize("key", ["", "   "])
def test_invalid_action_key_does_not_write(service, method, key):
    with patch.object(service, "save_recovery_state") as save, patch.object(service, "append_event") as event:
        with pytest.raises(ValueError, match="idempotency_key"):
            getattr(service, method)(PATIENT_ID, "item", idempotency_key=key)
        save.assert_not_called()
        event.assert_not_called()


@pytest.mark.parametrize("value", [None, [], "invalid", 42])
def test_save_rejects_invalid_values(service, value):
    with patch.object(service, "table") as table:
        with pytest.raises(TypeError, match="RecoveryState dataclass or dictionary"):
            service.save_recovery_state(value)
        table.put_item.assert_not_called()


@pytest.fixture
def live_services(monkeypatch):
    # Rebind real tables explicitly even if an earlier unit test imported these
    # modules with boto3.resource mocked. Only integration tests use this fixture.
    import boto3
    from app import config
    state_service = import_module("app.database.recovery_state")
    event_service = import_module("app.database.event_history")
    dynamodb = boto3.resource("dynamodb", region_name=config.REGION)
    monkeypatch.setattr(state_service, "table", dynamodb.Table(config.RECOVERY_STATE_TABLE))
    monkeypatch.setattr(event_service, "event_table", dynamodb.Table(config.EVENT_HISTORY_TABLE))
    return state_service, event_service


@pytest.mark.integration
class TestLivePhase5Actions:
    def test_get_medications(self, live_services):
        state_service, _ = live_services
        assert isinstance(state_service.get_medications(PATIENT_ID), list)

    def test_get_tasks(self, live_services):
        state_service, _ = live_services
        assert isinstance(state_service.get_today_tasks(PATIENT_ID), list)

    def test_mark_medication_taken(self, live_services):
        state_service, _ = live_services
        medications = state_service.get_medications(PATIENT_ID)
        assert medications, "Demo patient needs at least one medication"
        result = state_service.mark_medication_taken(
            patient_id=PATIENT_ID, medication_id=medications[0]["id"],
            idempotency_key="phase5-test-med-001",
        )
        assert result["success"] is True
        assert result["medication"]["status"] == "completed"
        saved = state_service.table.get_item(Key={"patient_id": PATIENT_ID}, ConsistentRead=True)["Item"]
        assert state_service._find_medication(saved, medications[0]["id"])["status"] == "completed"

    def test_repeat_medication_action(self, live_services):
        state_service, _ = live_services
        medications = state_service.get_medications(PATIENT_ID)
        assert medications, "Demo patient needs at least one medication"
        # Establish the first action here; do not depend on test execution order.
        for _ in range(2):
            result = state_service.mark_medication_taken(
                patient_id=PATIENT_ID, medication_id=medications[0]["id"],
                idempotency_key="phase5-test-med-001",
            )
        assert result["already_completed"] is True

    def test_mark_task_completed(self, live_services):
        state_service, _ = live_services
        tasks = state_service.get_today_tasks(PATIENT_ID)
        assert tasks, "Demo patient needs at least one task"
        result = state_service.mark_task_completed(
            patient_id=PATIENT_ID, task_id=tasks[0]["id"],
            idempotency_key="phase5-test-task-001",
        )
        assert result["success"] is True
        assert result["task"]["status"] == "completed"
        saved = state_service.table.get_item(Key={"patient_id": PATIENT_ID}, ConsistentRead=True)["Item"]
        assert state_service._find_task(saved, tasks[0]["id"])["status"] == "completed"

    def test_get_events(self, live_services):
        _, event_service = live_services
        events = event_service.get_events(PATIENT_ID)
        assert isinstance(events, list)
        assert all(event["patient_id"] == PATIENT_ID for event in events)


def test_new_schema_state_survives_database_save_read_and_actions(service):
    """Exercise new fields end-to-end through storage/actions without contacting AWS."""
    from copy import deepcopy
    from dataclasses import asdict
    from boto3.dynamodb.types import TypeSerializer
    from app.ingestion.normalizer import normalize_recovery_plan
    from app.ingestion.validator import validate_recovery_plan

    source = {"snippet": "Synthetic evidence", "page": 1,
              "read_from_image": True, "document_id": "model-invented"}
    extracted = {
        "medications": [{"name": "Example", "strength": "500 mg", "dose": None,
                         "times_per_day": 2, "time_of_day": ["morning"], "as_needed": True,
                         "max_per_day": 4, "instructions": "Stated instruction", "source": source}],
        "tasks": [{"description": "Walk every morning", "kind": "walk",
                   "time_of_day": ["morning"], "clock_times": [], "details": "As stated",
                   "duration_text": "7 days", "source": source}],
        "appointments": [{"title": "Review", "date": "2026-10-01",
                          "conflicting_dates": ["2026-10-02"], "source": source}],
        "restrictions": [{"text": "Avoid lifting", "topic": "activity", "source": source}],
        "monitoring": [{"what": "Temperature", "frequency_text": "twice daily",
                        "threshold_text": "above 38.5 C", "source": source}],
        "warning_signs": [{"text": "Chest pain", "action": "Call 999 immediately",
                           "urgency": "emergency", "source": source}],
    }
    state = validate_recovery_plan(normalize_recovery_plan(extracted, "patient", "request-doc"))
    expected = asdict(state)
    assert state.ingestion_status == "ready"
    assert state.appointments[0].needs_confirmation is True
    # Check SDK serialization locally as well as dataclasses.asdict.
    assert TypeSerializer().serialize(expected)["M"]
    stored = {}

    def put_item(*, Item):
        stored.clear()
        stored.update(deepcopy(Item))
        return {}

    with patch.object(service, "table") as table, patch.object(service, "append_event") as event:
        table.put_item.side_effect = put_item
        table.get_item.side_effect = lambda **_: {"Item": deepcopy(stored)}
        event.return_value = {"created": True, "duplicate": False}
        service.save_recovery_state(state)
        assert stored == expected
        assert service.get_recovery_state("patient") == expected
        assert service.get_medications("patient") == expected["medications"]
        assert service.get_today_tasks("patient") == expected["tasks"]

        med = service.mark_medication_taken("patient", state.medications[0].id, "med-action")
        task = service.mark_task_completed("patient", state.tasks[0].id, idempotency_key="task-action")
        for category, result_key, result in [("medications", "medication", med), ("tasks", "task", task)]:
            completed = result[result_key]
            assert completed["status"] == "completed"
            for field, value in expected[category][0].items():
                if field != "status":
                    assert completed[field] == value
            assert stored[category][0] == completed
        for category in ("appointments", "restrictions", "monitoring", "warning_signs"):
            assert stored[category] == expected[category]
        assert event.call_count == 2
        assert service.mark_medication_taken("patient", state.medications[0].id, "med-action")["already_completed"]
        assert service.mark_task_completed("patient", state.tasks[0].id, idempotency_key="task-action")["already_completed"]
        assert event.call_count == 2
