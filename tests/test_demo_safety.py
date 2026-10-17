"""Regression checks for abuse limits and explicit medication withdrawal."""
from datetime import datetime
from io import BytesIO
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from pypdf import PdfWriter

from app.ingestion.pdf_processor import extract_text
from app.reminders.selector import find_due_reminder
from app.database import recovery_state


@pytest.mark.parametrize('flags', [
    {'status': 'stopped'}, {'status': 'discontinued'}, {'status': 'cancelled'},
    {'active': False}, {'stopped': True}, {'stopped_at': '2026-10-22T12:00:00Z'},
])
def test_withdrawn_medicine_cannot_be_reexpanded_or_reminded(monkeypatch, flags):
    med = {'id': 'withdrawn', 'name': 'Synthetic medicine', 'status': 'pending',
           'clock_time': '08:00', 'times_per_day': 1, **flags}
    monkeypatch.setattr(recovery_state, 'get_recovery_state', lambda _: {'medications': [med]})
    monkeypatch.setattr(recovery_state, 'get_events', lambda _: [])
    assert recovery_state.get_medications('isolated', '2026-10-23') == []
    now = datetime(2026, 10, 23, 7, 30, tzinfo=ZoneInfo('Europe/London'))
    assert find_due_reminder([], [med], now) is None
    assert find_due_reminder([], [med], now, force_next=True) is None


def test_medicine_after_explicit_end_never_becomes_reminder(monkeypatch):
    med = {'id': 'ended', 'end_date': '2026-10-22', 'status': 'pending'}
    monkeypatch.setattr(recovery_state, 'get_recovery_state', lambda _: {'medications': [med]})
    monkeypatch.setattr(recovery_state, 'get_events', lambda _: [])
    assert recovery_state.get_medications('isolated', '2026-10-23') == []


def test_public_pdf_validation_page_cap_and_encryption():
    writer = PdfWriter()
    for _ in range(21): writer.add_blank_page(width=72, height=72)
    data = BytesIO(); writer.write(data)
    with pytest.raises(ValueError, match='page limit'): extract_text(data.getvalue(), max_pages=20)
    writer = PdfWriter(); writer.add_blank_page(width=72, height=72); writer.encrypt('test-only')
    data = BytesIO(); writer.write(data)
    with pytest.raises(ValueError, match='Encrypted'): extract_text(data.getvalue(), max_pages=20)

@pytest.mark.parametrize('now_hour', [7, 9])
def test_engine_rejects_stopped_timed_missed_and_stale_scheduled_reminders(now_hour):
    from app.reminders.engine import choose_checkin, pending_is_valid
    now = datetime(2026, 10, 23, now_hour, 30, tzinfo=ZoneInfo('Europe/London'))
    dose = {'occurrence_id': 'withdrawn#2026-10-23#1', 'name': 'Synthetic medicine',
            'status': 'pending', 'active': False, 'time_of_day_label': 'morning', 'clock_time': '08:00'}
    pending = {'occurrence_id': dose['occurrence_id'], 'item_type': 'medication', 'text': 'Old reminder'}
    assert not pending_is_valid(pending, [], [dose], now)
    assert not pending_is_valid(pending, [], [], now)
    scheduled = {**pending, 'checkin_id': 'old', 'type': 'missed_dose', 'due_at': now.isoformat()}
    result = choose_checkin({'pending_checkin': pending, 'scheduled_checkins': [scheduled]}, [], [dose], now, now, None)
    assert result.checkin is None and result.expired
    dose.pop('clock_time')
    assert choose_checkin({}, [], [dose], now, now, None).checkin is None

@pytest.mark.parametrize('size,expected', [(4 * 1024 * 1024, 200), (4 * 1024 * 1024 + 1, 413)])
def test_bridge_pdf_byte_boundary_is_below_five_megabytes(monkeypatch, size, expected):
    from app import web_bridge
    from tests.bridge_client import BridgeClient
    def extract(data, **limits):
        assert len(data) <= 4 * 1024 * 1024
        assert limits == {'max_pages': 20, 'max_text_chars': 200_000}
        return [{'page': 1, 'text': 'Discharge summary. Take medications as prescribed.'}]
    monkeypatch.setattr(web_bridge, 'extract_pdf_text', extract)
    payload = b'%PDF-' + b' ' * (size - 5)
    assert BridgeClient(web_bridge.app).post('/documents/validate', content=payload).status_code == expected
