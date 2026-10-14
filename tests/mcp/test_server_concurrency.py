"""The MCP server's tools run their blocking work in threads, so requests overlap instead of queueing."""

import asyncio
import time

from app.mcp import server

SLOW_SECONDS = 0.3


def test_two_reads_overlap_instead_of_running_one_after_the_other(monkeypatch):
    def slow_read(context):
        time.sleep(SLOW_SECONDS)  # a blocking DynamoDB read
        return {"ok": True, "data": {}}

    monkeypatch.setattr(server, "get_current_patient_context", lambda: object())
    monkeypatch.setattr(server, "get_today_tasks_for_context", slow_read)
    monkeypatch.setattr(server, "get_medications_for_context", slow_read)

    async def both():
        start = time.perf_counter()
        await asyncio.gather(server.get_today_tasks(), server.get_medications())
        return time.perf_counter() - start

    elapsed = asyncio.run(both())

    # Run one after the other this would take 2 x 0.3 s.
    assert elapsed < SLOW_SECONDS * 1.7


def test_a_tool_still_returns_its_result_and_sees_the_patient(monkeypatch):
    patient = object()
    seen = []

    def read(context, query):
        seen.append((context, query))
        return {"ok": True, "data": {"matches": []}}

    monkeypatch.setattr(server, "get_current_patient_context", lambda: patient)
    monkeypatch.setattr(server, "search_discharge_instructions_for_context", read)

    result = asyncio.run(server.search_discharge_instructions("driving"))

    assert result == {"ok": True, "data": {"matches": []}}
    assert seen == [(patient, "driving")]
