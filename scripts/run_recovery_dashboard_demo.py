"""Read-only isolated dashboard bridge on 8003. Memory by default; never writes AWS.

Use AGENT_API_URL=http://127.0.0.1:8003 when starting Next.js. Only weekly/day
read routes are exposed, behind the existing BRIDGE_KEY authentication.
"""
import argparse
from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.recovery_dashboard_seed import PATIENT, NOW, build_seed


def build_app(stack, read_state, read_events):
    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.routing import Route
    from app import web_bridge
    from app.auth.bridge_auth import BridgeAuthenticationMiddleware
    from app.auth.patient_scope import PatientContext
    from app.mcp.context import set_current_patient_context, reset_current_patient_context
    from app.mcp import server
    from app.mcp.tools import recovery, recovery_day, week
    from app.database import recovery_state
    for module in (recovery, recovery_day, week, recovery_state):
        stack.enter_context(patch.object(module, "get_recovery_state", read_state))
    for module in (recovery_day, week):
        stack.enter_context(patch.object(module, "get_complete_patient_events", read_events))
    stack.enter_context(patch.object(recovery_state, "get_events", read_events))

    async def call(name, arguments):
        allowed = {"get_week_summary": server.get_week_summary, "get_recovery_day_details": server.get_recovery_day_details}
        if name not in allowed:
            raise ValueError("Only dashboard reads are available")
        token = set_current_patient_context(PatientContext("isolated-dashboard", PATIENT, "isolated-dashboard"))
        try:
            return SimpleNamespace(structured_content=await allowed[name](**arguments))
        finally:
            reset_current_patient_context(token)
    stack.enter_context(patch.object(web_bridge, "call_mcp_tool", call))
    return Starlette(routes=[Route("/bridge/health", web_bridge.bridge_health),
        Route("/week-summary", web_bridge.week_summary), Route("/recovery-day", web_bridge.recovery_day)],
        middleware=[Middleware(BridgeAuthenticationMiddleware)])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8003)
    parser.add_argument("--read-aws", action="store_true", help="Opt in to read-only DynamoDB access for isolated_week_demo only")
    parser.add_argument("--region")
    parser.add_argument("--state-table")
    parser.add_argument("--event-table")
    args = parser.parse_args()
    with ExitStack() as stack:
        stack.enter_context(patch.dict(os.environ, {"CLOCK_MODE": "demo", "DEMO_FIXED_NOW": NOW,
            "LOCAL_REMINDER_LOOP": "0", "DEMO_IDLE_RESET_HOURS": "0"}))
        if not args.read_aws:
            stack.enter_context(patch.dict(os.environ, {"AWS_ACCESS_KEY_ID": "isolated-test-only",
                "AWS_SECRET_ACCESS_KEY": "isolated-test-only", "AWS_EC2_METADATA_DISABLED": "true"}))
            from botocore.client import BaseClient
            def forbidden(*args, **kwargs): raise RuntimeError("AWS is forbidden in memory mode")
            stack.enter_context(patch.object(BaseClient, "_make_api_call", forbidden))
            plan, rows = build_seed()
            def read_state(patient):
                if patient != PATIENT: raise ValueError("Wrong isolated patient")
                return deepcopy(plan)
            def read_events(patient):
                if patient != PATIENT: raise ValueError("Wrong isolated patient")
                return deepcopy(rows)
            print("Isolated dashboard: MEMORY fixture, not DynamoDB verification.")
        else:
            if not all([args.region, args.state_table, args.event_table]):
                parser.error("--read-aws requires --region, --state-table and --event-table")
            import boto3
            from boto3.dynamodb.conditions import Key
            db = boto3.resource("dynamodb", region_name=args.region)
            state_table, event_table = db.Table(args.state_table), db.Table(args.event_table)
            def read_state(patient):
                if patient != PATIENT: raise ValueError("Wrong isolated patient")
                plan = state_table.get_item(Key={"patient_id": PATIENT}, ConsistentRead=True).get("Item")
                if not plan or plan.get("synthetic") is not True:
                    raise ValueError("Expected dedicated synthetic plan")
                return plan
            def read_events(patient):
                if patient != PATIENT: raise ValueError("Wrong isolated patient")
                rows = []
                query = {"KeyConditionExpression": Key("patient_id").eq(PATIENT), "ConsistentRead": True}
                while True:
                    page = event_table.query(**query)
                    rows.extend(e for e in page.get("Items", []) if e.get("patient_id") == PATIENT)
                    if not page.get("LastEvaluatedKey"): return rows
                    query["ExclusiveStartKey"] = page["LastEvaluatedKey"]
            print("Isolated dashboard: READ-ONLY DynamoDB, dedicated synthetic patient only.")
        app = build_app(stack, read_state, read_events)
        from scripts.run_web_bridge import configure_local_tls_trust
        configure_local_tls_trust()
        import uvicorn
        uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
