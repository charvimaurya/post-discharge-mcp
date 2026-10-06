"""Test request-scoped PatientContext handling."""

import asyncio

import pytest

from app.auth.patient_scope import PatientContext
from app.mcp.context import (
    get_current_patient_context,
    reset_current_patient_context,
    set_current_patient_context,
)


def test_no_context_raises():
    with pytest.raises(RuntimeError):
        get_current_patient_context()


def test_set_and_reset_context():
    context = PatientContext("user", "patient_a", "session")
    token = set_current_patient_context(context)
    try:
        assert get_current_patient_context() == context
    finally:
        reset_current_patient_context(token)

    with pytest.raises(RuntimeError):
        get_current_patient_context()


def test_concurrent_requests_keep_their_own_patient():
    async def request(patient_id):
        token = set_current_patient_context(PatientContext("user", patient_id, "session"))
        try:
            await asyncio.sleep(0)
            return get_current_patient_context().patient_id
        finally:
            reset_current_patient_context(token)

    async def main():
        return await asyncio.gather(request("patient_a"), request("patient_b"))

    assert asyncio.run(main()) == ["patient_a", "patient_b"]


def test_tool_uses_request_context(monkeypatch):
    from app.mcp import server
    from app.mcp.tools import recovery

    monkeypatch.setattr(recovery, "get_recovery_state", lambda patient_id: {"patient_id": patient_id})
    token = set_current_patient_context(PatientContext("user", "patient_from_request", "session"))
    try:
        result = asyncio.run(server.get_recovery_plan())
    finally:
        reset_current_patient_context(token)

    assert result["data"]["patient_id"] == "patient_from_request"


def test_tool_without_request_context_raises():
    from app.mcp import server

    with pytest.raises(RuntimeError):
        asyncio.run(server.get_recovery_plan())
