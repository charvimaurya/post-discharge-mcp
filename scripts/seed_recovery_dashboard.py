"""Opt-in seed for isolated_week_demo only. Default mode is a no-AWS preview.

Never resets Margaret or changes existing records. Requires explicit table names.
"""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.recovery_dashboard_seed import PATIENT, build_seed


def seed_tables(state_table, event_table):
    from boto3.dynamodb.conditions import Key
    from botocore.exceptions import ClientError
    plan, events = build_seed()
    existing = state_table.get_item(Key={"patient_id": PATIENT}, ConsistentRead=True).get("Item")
    if existing is not None and existing != plan:
        raise ValueError("Refusing to overwrite an existing or differently owned plan")
    expected = {e["timestamp"]: e for e in events}
    args = {"KeyConditionExpression": Key("patient_id").eq(PATIENT), "ConsistentRead": True}
    while True:
        page = event_table.query(**args)
        if any(e != expected.get(e.get("timestamp")) for e in page.get("Items", [])):
            raise ValueError("Refusing to mix existing history with the synthetic fixture")
        if not page.get("LastEvaluatedKey"):
            break
        args["ExclusiveStartKey"] = page["LastEvaluatedKey"]
    def put_once(table, item, key):
        try:
            table.put_item(Item=item, ConditionExpression="attribute_not_exists(patient_id)")
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                raise
            if table.get_item(Key=key, ConsistentRead=True).get("Item") != item:
                raise ValueError("Existing record conflicts with the synthetic fixture") from None
    put_once(state_table, plan, {"patient_id": PATIENT})
    for event in events:
        put_once(event_table, event, {"patient_id": PATIENT, "timestamp": event["timestamp"]})
    return len(events)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", action="store_true", help="Explicitly allow conditional writes for the dedicated synthetic patient")
    parser.add_argument("--region")
    parser.add_argument("--state-table")
    parser.add_argument("--event-table")
    args = parser.parse_args()
    plan, events = build_seed()
    if not args.confirm:
        print(f"Preview only: {PATIENT}, 20–23 October 2026, {len(events)} synthetic events. No AWS calls.")
        return
    if not all([args.region, args.state_table, args.event_table]) or args.state_table == args.event_table:
        parser.error("--confirm requires --region and distinct --state-table / --event-table")
    import boto3
    db = boto3.resource("dynamodb", region_name=args.region)
    count = seed_tables(db.Table(args.state_table), db.Table(args.event_table))
    print(f"Synthetic fixture verified: {PATIENT}, {count} events. Existing records were not overwritten.")


if __name__ == "__main__":
    main()
