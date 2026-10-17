"""Real-clock integration through the bridge and plan readers, without AWS."""
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import ast

import pytest
from tests.bridge_client import BridgeClient as TestClient

from app import clock, web_bridge
from app.database import recovery_state
from app.mcp.tools import actions, recovery
from lambdas.reminder_checker import handler


@pytest.fixture
def real_plan(monkeypatch):
    monkeypatch.setenv('CLOCK_MODE', 'real')
    monkeypatch.setenv('DEMO_FIXED_NOW', clock.DEFAULT_DEMO_NOW)
    state = {
        'timezone': 'Europe/London', 'discharge_date': '2026-10-16',
        'first_name': 'Margaret',
        'tasks': [{'id': 'task_walk', 'description': 'Short walk',
                   'times_per_day': 2, 'clock_times': ['07:30', '15:00']}],
        'medications': [{'id': 'med_codeine', 'name': 'Codeine',
                         'as_needed': True, 'duration_text': 'Stop after 5 days.'}],
    }
    events = []
    for module in (recovery_state, recovery, actions, handler, web_bridge):
        monkeypatch.setattr(module, 'get_recovery_state', lambda patient_id: state)
    monkeypatch.setattr(recovery_state, 'get_events', lambda patient_id: events)
    monkeypatch.setattr(handler, 'save_pending_checkin', lambda *args, **rules: True)

    async def call(name, arguments):
        context = SimpleNamespace(patient_id='demo_patient_001')
        fn = recovery.get_today_tasks_for_context if name == 'get_today_tasks' else recovery.get_medications_for_context
        return SimpleNamespace(structured_content=fn(context))

    monkeypatch.setattr(web_bridge, 'call_mcp_tool', call)
    def freeze(value):
        instant = datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
        monkeypatch.setattr(clock, 'system_now_utc', lambda: instant)
    freeze('2026-11-02T14:20:00')
    return state, events, freeze


def test_real_today_builds_current_occurrences(real_plan):
    result = TestClient(web_bridge.app).get('/today').json()
    assert result['date'] == '2026-11-02'
    assert result['clock_label'] == 'Monday 2 November, 14:20'
    assert [t['occurrence_id'] for t in result['tasks']] == ['task_walk#2026-11-02#1', 'task_walk#2026-11-02#2']
    assert result['tasks'][0]['timing'] == 'earlier today'
    assert result['tasks'][1]['status'] == 'pending'
    assert result['medications'] == []
    assert recovery_state.get_medications('demo_patient_001') == []


@pytest.mark.parametrize('time,created', [('14:31', True), ('14:10', False)])
def test_real_reminder_window(real_plan, time, created):
    real_plan[2](f'2026-11-02T{time}:00')
    result = TestClient(web_bridge.app).post('/reminders/check').json()
    assert result['created'] is created
    if created:
        assert result['pending_checkin']['occurrence_id'] == 'task_walk#2026-11-02#2'
        assert result['pending_checkin']['text'].startswith('Good afternoon')


@pytest.mark.parametrize('time', ['00:10', '14:10', '23:50'])
def test_force_next_at_any_time(real_plan, time):
    real_plan[2](f'2026-11-02T{time}:00')
    result = TestClient(web_bridge.app).post('/reminders/check?force_next=true').json()
    assert result['created'] is True
    if time == '14:10':
        assert result['pending_checkin']['occurrence_id'] == 'task_walk#2026-11-02#2'
        assert result['pending_checkin']['text'].startswith('Good afternoon')


def test_force_disabled_in_production(real_plan, monkeypatch):
    monkeypatch.setenv('CLOCK_MODE', 'production')
    assert TestClient(web_bridge.app).post('/reminders/check?force_next=true').status_code == 403
    assert handler.handler({'force_next': True}, None)['reason'] == 'force_next_disabled'


def test_completion_is_per_date(real_plan):
    _, events, freeze = real_plan
    events.append({'event_type': 'task_completed', 'details': {
        'occurrence_id': 'task_walk#2026-11-02#1', 'date': '2026-11-02', 'completed_at': '2026-11-02T08:00:00Z'}})
    assert recovery_state.get_today_tasks('demo_patient_001')[0]['status'] == 'completed'
    freeze('2026-11-03T14:20:00')
    assert all(t['status'] == 'pending' for t in recovery_state.get_today_tasks('demo_patient_001'))


def test_timezone_date_used_by_read_and_report_tools(real_plan, monkeypatch):
    state, _, freeze = real_plan
    state['timezone'] = 'Asia/Tokyo'
    freeze('2026-11-02T23:20:00')
    context = SimpleNamespace(patient_id='demo_patient_001')
    assert recovery.get_today_tasks_for_context(context)['data']['date'] == '2026-11-03'
    captured = []
    monkeypatch.setattr(actions, 'mark_task_completed', lambda patient, occurrence, day: captured.append(day) or {'already_completed': False})
    actions.report_task_completed_for_context(context, 'task_walk#2026-11-03#1')
    assert captured == ['2026-11-03']


def test_default_real_and_explicit_demo(monkeypatch):
    monkeypatch.delenv('CLOCK_MODE', raising=False)
    monkeypatch.setattr(clock, 'system_now_utc', lambda: datetime(2026, 11, 2, 14, 20, tzinfo=timezone.utc))
    assert clock.get_patient_datetime().day == 2
    monkeypatch.setenv('CLOCK_MODE', 'demo')
    monkeypatch.delenv('DEMO_FIXED_NOW', raising=False)
    assert clock.get_clock_label() == 'Friday 23 October, 07:00'


def test_only_clock_reads_system_time():
    for root in ('app', 'lambdas', 'scripts'):
        for path in Path(root).rglob('*.py'):
            if path == Path('app/clock.py'):
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    assert node.func.attr not in {'now', 'utcnow', 'today'}, str(path)
                    assert not (node.func.attr == 'time' and isinstance(node.func.value, ast.Name) and node.func.value.id == 'time'), str(path)


def test_medication_end_date_boundary(real_plan):
    assert recovery_state.get_medications('demo_patient_001', '2026-10-20')
    assert recovery_state.get_medications('demo_patient_001', '2026-10-21') == []


@pytest.mark.parametrize('mode,day', [('real', '2026-11-02'), ('demo', '2026-10-23')])
def test_reset_only_current_date_completions(real_plan, monkeypatch, mode, day):
    from app import demo_reset
    from scripts import reset_demo_patient as reset
    monkeypatch.setenv('CLOCK_MODE', mode)
    monkeypatch.setenv('DEMO_FIXED_NOW', clock.DEFAULT_DEMO_NOW)
    state = real_plan[0]
    monkeypatch.setattr(demo_reset, 'get_recovery_state', lambda patient_id: state)
    monkeypatch.setattr(demo_reset, 'save_recovery_state', lambda state: None)
    deleted = []
    rows = [
        {'patient_id': reset.PATIENT_ID, 'timestamp': 'today', 'event_type': 'task_completed',
         'details': {'occurrence_id': f'task_walk#{day}#1'}},
        {'patient_id': reset.PATIENT_ID, 'timestamp': 'older', 'event_type': 'task_completed',
         'details': {'occurrence_id': 'task_walk#2026-10-19#1'}},
        {'patient_id': reset.PATIENT_ID, 'timestamp': 'other', 'event_type': 'other',
         'details': {'occurrence_id': f'task_walk#{day}#1'}},
    ]
    class Table:
        def batch_writer(self): return self
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def query(self, **kwargs):
            if 'ExclusiveStartKey' in kwargs:
                return {'Items': rows[1:]}
            return {'Items': rows[:1], 'LastEvaluatedKey': {'timestamp': 'today'}}
        def delete_item(self, Key): deleted.append(Key['timestamp'])
    monkeypatch.setattr(demo_reset, 'event_table', Table())
    monkeypatch.setattr('sys.argv', ['reset_demo_patient.py', '--confirm'])
    reset.main()
    assert deleted == ['today']


@pytest.mark.parametrize('time,greeting', [
    ('09:00', 'Good morning, Margaret. I hope you slept well.'),
    ('12:00', "Good afternoon, Margaret. I hope you're doing well."),
    ('18:00', "Good evening, Margaret. I hope you're doing well."),
])
def test_opening_greeting_on_empty_pre_discharge_day(real_plan, time, greeting):
    real_plan[2](f'2026-10-10T{time}:00')
    result = TestClient(web_bridge.app).get('/today').json()
    assert result['opening_greeting'] == greeting
    assert result['tasks'] == []
    assert result['medications'] == []
    assert result['pending_checkin'] is None


def test_opening_greeting_uses_patient_timezone(real_plan):
    real_plan[0]['timezone'] = 'Asia/Tokyo'
    result = TestClient(web_bridge.app).get('/today').json()
    assert result['opening_greeting'].startswith('Good evening, Margaret.')


def test_opening_greeting_without_name(real_plan):
    real_plan[0].pop('first_name')
    result = TestClient(web_bridge.app).get('/today').json()
    assert result['opening_greeting'].startswith("Good afternoon. I hope you're doing well.")


def test_opening_names_next_walk_not_earlier_walk(real_plan):
    result = TestClient(web_bridge.app).get('/today').json()
    assert result['opening_greeting'] == (
        "Good afternoon, Margaret. I hope you're doing well. "
        "Next is your afternoon walk at three o'clock."
    )


def test_demo_opening_uses_plan_time(real_plan, monkeypatch):
    monkeypatch.setenv('CLOCK_MODE', 'demo')
    monkeypatch.setenv('DEMO_FIXED_NOW', clock.DEFAULT_DEMO_NOW)
    result = TestClient(web_bridge.app).get('/today').json()
    assert result['opening_greeting'] == (
        'Good morning, Margaret. I hope you slept well. '
        'Next is your morning walk at half past seven. You can start getting ready.'
    )


def test_opening_skips_completed_and_unconfirmed_items(real_plan):
    state, events, _ = real_plan
    state['tasks'][0]['needs_confirmation'] = True
    assert 'Next is' not in TestClient(web_bridge.app).get('/today').json()['opening_greeting']
    state['tasks'][0]['needs_confirmation'] = False
    events.append({'event_type': 'task_completed', 'details': {
        'occurrence_id': 'task_walk#2026-11-02#2', 'date': '2026-11-02',
        'completed_at': '2026-11-02T14:00:00Z'}})
    assert 'Next is' not in TestClient(web_bridge.app).get('/today').json()['opening_greeting']


def test_opening_medication_uses_take_language(real_plan):
    state, _, freeze = real_plan
    state['tasks'] = []
    state['medications'] = [{
        'id': 'med_thinner', 'name': 'Blood thinner', 'dose': '1 tablet',
        'times_per_day': 1, 'time_of_day': ['evening'],
    }]
    freeze('2026-11-02T18:00:00')
    result = TestClient(web_bridge.app).get('/today').json()
    assert result['opening_greeting'] == (
        "Good evening, Margaret. I hope you're doing well. "
        'You need to take 1 tablet of your blood thinner this evening.'
    )
