"""Save live resource settings locally before migrating AWS resource names."""

import json
import sys
from pathlib import Path

import boto3

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.clock import system_now_utc


def main():
    session = boto3.Session(region_name="eu-west-2")
    account = session.client("sts").get_caller_identity()["Account"]
    if account != "992617582533":
        raise RuntimeError("Unexpected AWS account; stopping inventory")
    target = Path("infra/security/backup/name-migration") / system_now_utc().strftime("%Y%m%dT%H%M%SZ")
    target.mkdir(parents=True, mode=0o700)

    def save(name, value):
        path = target / f"{name}.json"
        path.write_text(json.dumps(value, indent=2, default=str))
        path.chmod(0o600)

    def read(name, operation, **kwargs):
        try:
            result = operation(**kwargs)
            result.pop("ResponseMetadata", None)
            save(name, result)
            print(f"Saved {name}", flush=True)
            return result
        except Exception as exc:
            code = getattr(exc, "response", {}).get("Error", {}).get("Code", type(exc).__name__)
            save(name, {"inventory_error": code})
            print(f"Could not read {name}: {code}", flush=True)
            return {}

    s3 = session.client("s3")
    bucket = f"afterward-documents-{account}-london"
    for label, method in [("location", "get_bucket_location"), ("encryption", "get_bucket_encryption"), ("policy", "get_bucket_policy"), ("lifecycle", "get_bucket_lifecycle_configuration"), ("public-access", "get_public_access_block"), ("notifications", "get_bucket_notification_configuration"), ("versioning", "get_bucket_versioning")]:
        read(f"s3-{label}", getattr(s3, method), Bucket=bucket)
    count = size = 0
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket):
        for item in page.get("Contents", []):
            count += 1
            size += item["Size"]
    save("s3-volume", {"objects": count, "bytes": size})
    print(f"Letters bucket: {count} objects, {size} bytes", flush=True)
    sqs = session.client("sqs")
    for name in ["AfterWardDocumentProcessing", "AfterWardDocumentProcessingDLQ"]:
        queue = read(f"{name}-url", sqs.get_queue_url, QueueName=name)
        if queue.get("QueueUrl"):
            read(f"{name}-attributes", sqs.get_queue_attributes, QueueUrl=queue["QueueUrl"], AttributeNames=["All"])
            read(f"{name}-tags", sqs.list_queue_tags, QueueUrl=queue["QueueUrl"])
    lam = session.client("lambda")
    for name in ["AfterWardDocumentProcessor", "AfterwardReminderChecker"]:
        read(f"{name}-function", lam.get_function, FunctionName=name)
        read(f"{name}-event-mappings", lam.list_event_source_mappings, FunctionName=name)
        read(f"{name}-concurrency", lam.get_function_concurrency, FunctionName=name)
    iam = session.client("iam")
    for name in ["AfterWardDocumentProcessorRole", "AfterWardEcsTaskRole"]:
        read(f"{name}-role", iam.get_role, RoleName=name)
        read(f"{name}-attached-policies", iam.list_attached_role_policies, RoleName=name)
        policies = read(f"{name}-inline-policies", iam.list_role_policies, RoleName=name)
        for policy in policies.get("PolicyNames", []):
            read(f"{name}-policy-{policy}", iam.get_role_policy, RoleName=name, PolicyName=policy)
    vectors = session.client("s3vectors")
    vb = f"afterward-vectors-{account}-london"
    read("vector-bucket", vectors.get_vector_bucket, vectorBucketName=vb)
    read("vector-index", vectors.get_index, vectorBucketName=vb, indexName="afterward-discharge-index")
    kms = session.client("kms")
    key = read("kms-key", kms.describe_key, KeyId="alias/afterward-patient-data")
    if key.get("KeyMetadata"):
        read("kms-policy", kms.get_key_policy, KeyId=key["KeyMetadata"]["KeyId"], PolicyName="default")
    ecs = session.client("ecs")
    clusters = read("ecs-clusters", ecs.list_clusters)
    for index, cluster in enumerate(clusters.get("clusterArns", [])):
        services = read(f"ecs-services-{index}", ecs.list_services, cluster=cluster)
        names = services.get("serviceArns", [])
        for offset in range(0, len(names), 10):
            info = read(f"ecs-service-details-{index}-{offset}", ecs.describe_services, cluster=cluster, services=names[offset:offset+10])
            for service in info.get("services", []):
                read(f"ecs-task-{service['serviceName']}", ecs.describe_task_definition, taskDefinition=service["taskDefinition"])
    read("reminder-schedule", session.client("scheduler").get_schedule, Name="afterward-reminder-checker")
    print(f"Inventory directory: {target}", flush=True)


if __name__ == "__main__":
    main()
