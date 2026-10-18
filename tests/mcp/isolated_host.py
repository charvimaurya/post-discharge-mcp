"""Test-only MCPJam host. Memory storage, no AWS calls, loopback only.

Run: python -m tests.mcp.isolated_host --token-file /private/tmp/your-token-file
The token file must be newly created; its value is never printed.
"""
import argparse
from copy import deepcopy
import os
from pathlib import Path
import secrets
import signal
from types import SimpleNamespace

from botocore.client import BaseClient
from botocore.exceptions import ClientError

PATIENT = "isolated_mcpjam_s4"


class MemoryStore:
    def __init__(self):
        self.plan = {
            "patient_id": PATIENT, "timezone": "Europe/London",
            "tasks": [
                {"id": "walk", "description": "Synthetic walk", "times_per_day": 2,
                 "clock_times": ["08:00", "14:00"]},
                {"id": "confirm", "description": "Confirm synthetic exercise plan",
                 "needs_confirmation": True, "clock_times": ["09:00"]},
            ],
        }
        self.events = {}

    def get_item(self, *, Key, ConsistentRead=False):
        assert Key == {"patient_id": PATIENT}, "Only isolated patient is allowed"
        return {"Item": deepcopy(self.plan)}

    def query(self, *, KeyConditionExpression, ConsistentRead=False):
        assert KeyConditionExpression.get_expression()["values"][1] == PATIENT
        return {"Items": deepcopy(list(self.events.values()))}

    def put_item(self, *, Item, ConditionExpression, ExpressionAttributeNames):
        assert Item["patient_id"] == PATIENT
        assert ConditionExpression and ExpressionAttributeNames
        key = Item["timestamp"]
        if key in self.events:
            raise ClientError({"Error": {"Code": "ConditionalCheckFailedException"}}, "PutItem")
        self.events[key] = deepcopy(Item)
        return {}


def forbid_aws(*args, **kwargs):
    raise RuntimeError("AWS is prohibited in the isolated MCPJam host")


def build_app(patches, token, with_week=False):
    """Apply reversible process-local test patches; never alter production files."""
    patches.setattr(BaseClient, "_make_api_call", forbid_aws)
    for key, value in {
        "AWS_ACCESS_KEY_ID": "isolated-test-only", "AWS_SECRET_ACCESS_KEY": "isolated-test-only",
        "AWS_SESSION_TOKEN": "isolated-test-only", "AWS_EC2_METADATA_DISABLED": "true",
        "AWS_SHARED_CREDENTIALS_FILE": os.devnull, "AWS_CONFIG_FILE": os.devnull,
        "AWS_REGION": "eu-west-2", "CLOCK_MODE": "demo",
        "DEMO_FIXED_NOW": "2026-10-23T08:00:00+01:00", "LOCAL_REMINDER_LOOP": "0",
    }.items():
        patches.setenv(key, value)

    from app.auth.patient_scope import PatientContext
    from app.database import event_history, recovery_state
    from app.mcp import http_auth, http_server, server

    store = MemoryStore()
    if with_week:
        from tests.mcp.week_seed import seed_week_events
        from app.clock import get_current_datetime
        store.events = {row["timestamp"]: row for row in seed_week_events(PATIENT, get_current_datetime())}
    patches.setattr(recovery_state, "table", SimpleNamespace(get_item=store.get_item))
    patches.setattr(event_history, "event_table", SimpleNamespace(query=store.query, put_item=store.put_item))
    patches.setattr(http_auth, "get_expected_mcp_token", lambda: token)
    patches.setattr(http_auth, "PatientContext", lambda **kwargs: PatientContext(
        "isolated_test_user", PATIENT, "isolated_test_session"))

    def disabled(*args, **kwargs):
        raise RuntimeError("This tool is disabled in the isolated S4 host")

    for name in dir(server):
        if name.endswith("_for_context") and name not in {
            "get_today_tasks_for_context", "report_task_completed_for_context", "get_week_summary_for_context",
        }:
            patches.setattr(server, name, disabled)
    return http_server.app, store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--with-week", action="store_true", help="Seed synthetic history in memory only")
    args = parser.parse_args()
    token = secrets.token_urlsafe(32)
    descriptor = os.open(args.token_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        handle.write(token)
    import pytest
    import uvicorn

    def terminate(signum, frame):
        # Uvicorn re-raises captured SIGTERM after shutdown; exit through finally.
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, terminate)
    try:
        with pytest.MonkeyPatch.context() as patches:
            app, _ = build_app(patches, token, with_week=args.with_week)
            uvicorn.run(app, host="127.0.0.1", port=18001, access_log=False, log_level="warning")
    finally:
        args.token_file.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
