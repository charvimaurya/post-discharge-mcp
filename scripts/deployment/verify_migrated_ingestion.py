"""Upload a synthetic fixture for an isolated patient and verify the new AWS path."""

import json
import time
from pathlib import Path

import boto3


def main():
    s = boto3.Session(region_name="eu-west-2")
    patient = "migration_check_20261013"
    document = "afterward_name_migration"
    key = f"patients/{patient}/documents/{document}.pdf"
    s.client("s3").upload_file(str(Path("test_data/doc_001.pdf")), "afterward-documents-992617582533-london", key, ExtraArgs={"ContentType": "application/pdf"})
    print("Uploaded synthetic fixture for an isolated migration-check patient", flush=True)
    table = s.resource("dynamodb").Table("PostDischargeRecoveryState")
    for attempt in range(90):
        item = table.get_item(Key={"patient_id": patient}).get("Item", {})
        status = item.get("ingestion_status")
        if attempt % 6 == 0:
            print(f"Processing status: {status or 'waiting'}", flush=True)
        if status == "ready" and item.get("document_id") == document:
            break
        time.sleep(5)
    else:
        raise RuntimeError("Synthetic upload did not reach ready state")
    c = s.client("s3vectors")
    found = []
    kwargs = dict(vectorBucketName="afterward-vectors-992617582533-london", indexName="afterward-discharge-index", returnMetadata=True, maxResults=500)
    while True:
        page = c.list_vectors(**kwargs)
        found.extend(v for v in page.get("vectors", []) if v.get("metadata", {}).get("patient_id") == patient)
        if not page.get("nextToken"):
            break
        kwargs["nextToken"] = page["nextToken"]
    if not found:
        raise RuntimeError("Ready test document has no vectors in the new index")
    print(f"New S3 → SQS → Lambda → ready DynamoDB plan → S3 Vectors verified ({len(found)} chunks)", flush=True)
    result = s.client("lambda").invoke(FunctionName="AfterwardReminderChecker", Payload=json.dumps({"patient_id": patient}).encode())
    payload = json.loads(result["Payload"].read())
    if result.get("FunctionError"):
        raise RuntimeError("Reminder Lambda failed")
    print(f"Reminder Lambda succeeded; check-in created={bool(payload.get('created'))}", flush=True)
    schedule = s.client("scheduler").get_schedule(Name="afterward-reminder-checker")
    assert schedule["State"] == "ENABLED"
    print("Reminder schedule remains enabled", flush=True)


if __name__ == "__main__":
    main()
