"""Prepare, verify, and switch AfterWard resource replacements without deleting sources."""

import argparse
import hashlib
import json
import ssl
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import boto3
import certifi
from botocore.exceptions import ClientError


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "deployment/name-migration"
BACKUP = ROOT / "infra/security/backup/name-migration"
STATE = BACKUP / "migration-state.json"
NAMES = json.loads((CONFIG / "resource-names.json").read_text())["replacements"]
SOURCE_NAMES = {target: source for source, target in NAMES.items()}
OLD_BUCKET = SOURCE_NAMES["afterward-documents-992617582533-london"]
NEW_BUCKET = NAMES[OLD_BUCKET]
OLD_VB = SOURCE_NAMES["afterward-vectors-992617582533-london"]
NEW_VB = NAMES[OLD_VB]
OLD_INDEX = SOURCE_NAMES["afterward-discharge-index"]
NEW_INDEX = NAMES[OLD_INDEX]
OLD_FUNCTION = SOURCE_NAMES["AfterWardDocumentProcessor"]
NEW_FUNCTION = NAMES[OLD_FUNCTION]
OLD_ROLE = SOURCE_NAMES["AfterWardDocumentProcessorRole"]
NEW_ROLE = NAMES[OLD_ROLE]


def replace(value):
    text = json.dumps(value)
    for old, new in NAMES.items():
        text = text.replace(old, new)
    return json.loads(text)


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps(value, indent=2, default=str))
    path.chmod(0o600)


def create(operation, **kwargs):
    try:
        return operation(**kwargs)
    except ClientError as exc:
        if exc.response["Error"]["Code"] not in {"BucketAlreadyOwnedByYou", "ConflictException", "EntityAlreadyExists", "ResourceConflictException"}:
            raise
        return None


def objects(s3, bucket):
    return {item["Key"]: item for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket) for item in page.get("Contents", [])}


def digest(s3, bucket, key):
    body = s3.get_object(Bucket=bucket, Key=key)["Body"]
    try:
        return hashlib.sha256(body.read()).hexdigest()
    finally:
        body.close()


def vectors(client, bucket, index):
    result = {}
    kwargs = dict(vectorBucketName=bucket, indexName=index, maxResults=500, returnData=True, returnMetadata=True)
    while True:
        page = client.list_vectors(**kwargs)
        for item in page.get("vectors", []):
            result[item["key"]] = {k: item[k] for k in ("key", "data", "metadata") if k in item}
        if not page.get("nextToken"):
            return result
        kwargs["nextToken"] = page["nextToken"]


def sync_data(s3, vc):
    source = objects(s3, OLD_BUCKET)
    def copy_letter(key):
        source_hash = digest(s3, OLD_BUCKET, key)
        try:
            same = digest(s3, NEW_BUCKET, key) == source_hash
        except ClientError as exc:
            if exc.response["Error"]["Code"] not in {"NoSuchKey", "404"}:
                raise
            same = False
        if not same:
            s3.copy_object(Bucket=NEW_BUCKET, Key=key, CopySource={"Bucket": OLD_BUCKET, "Key": key})
        if digest(s3, NEW_BUCKET, key) != source_hash:
            raise RuntimeError("Copied letter content verification failed")
    with ThreadPoolExecutor(max_workers=8) as workers:
        for number, _ in enumerate(workers.map(copy_letter, source), 1):
            if number % 25 == 0:
                print(f"Verified {number}/{len(source)} letter objects", flush=True)
    if not set(source).issubset(objects(s3, NEW_BUCKET)):
        raise RuntimeError("Destination is missing letter objects")
    data = vectors(vc, OLD_VB, OLD_INDEX)
    values = list(data.values())
    for offset in range(0, len(values), 100):
        vc.put_vectors(vectorBucketName=NEW_VB, indexName=NEW_INDEX, vectors=values[offset:offset + 100])
    # Vector writes may take a short time to become visible to reads.
    for attempt in range(10):
        copied = vectors(vc, NEW_VB, NEW_INDEX)
        if all(copied.get(key) == value for key, value in data.items()):
            break
        time.sleep(2)
    else:
        raise RuntimeError("Copied vector data/metadata verification failed")
    if data:
        sample = next(iter(data.values()))
        args = dict(queryVector=sample["data"], topK=5, returnMetadata=True, returnDistance=True)
        metadata = sample.get("metadata", {})
        if all(k in metadata for k in ("patient_id", "document_id")):
            args["filter"] = {"$and": [{k: {"$eq": metadata[k]}} for k in ("patient_id", "document_id")]}
        a = vc.query_vectors(vectorBucketName=OLD_VB, indexName=OLD_INDEX, **args)["vectors"]
        b = vc.query_vectors(vectorBucketName=NEW_VB, indexName=NEW_INDEX, **args)["vectors"]
        # Independently built approximate indexes may differ in lower-ranked hits.
        # All underlying vectors/metadata were compared above; check best evidence.
        if not a or not b or a[0]["key"] != b[0]["key"]:
            raise RuntimeError("Representative vector query best match differs")
        overlap = len({v["key"] for v in a} & {v["key"] for v in b})
        print(f"Search best match preserved; {overlap}/{len(a)} top results overlap", flush=True)
    print(f"Verified {len(source)} letter objects and {len(data)} vectors", flush=True)
    return {"copied_objects": len(source), "copied_vectors": len(data)}


def prepare(s, state):
    s3, vc, iam, sqs, lam = [s.client(name) for name in ("s3", "s3vectors", "iam", "sqs", "lambda")]
    create(s3.create_bucket, Bucket=NEW_BUCKET, CreateBucketConfiguration={"LocationConstraint": "eu-west-2"})
    for method, file in [("put_bucket_encryption", "s3-encryption.json"), ("put_public_access_block", "s3-public-access.json"), ("put_bucket_lifecycle_configuration", "s3-lifecycle.json")]:
        settings = json.loads((CONFIG / file).read_text())
        if method == "put_bucket_lifecycle_configuration":
            settings = {"LifecycleConfiguration": {"Rules": settings["Rules"]}}
        getattr(s3, method)(Bucket=NEW_BUCKET, **settings)
    s3.put_bucket_policy(Bucket=NEW_BUCKET, Policy=(CONFIG / "s3-bucket-policy.json").read_text())
    if s3.get_bucket_notification_configuration(Bucket=NEW_BUCKET).get("QueueConfigurations"):
        raise RuntimeError("Destination notifications already enabled; do not recopy historical letters")
    print("Created/configured AfterWard letters bucket", flush=True)
    source_vb = vc.get_vector_bucket(vectorBucketName=OLD_VB)["vectorBucket"]
    create(vc.create_vector_bucket, vectorBucketName=NEW_VB, encryptionConfiguration=source_vb["encryptionConfiguration"])
    create(vc.create_index, **json.loads((CONFIG / "vector-index.json").read_text()))
    source_index = vc.get_index(vectorBucketName=OLD_VB, indexName=OLD_INDEX)["index"]
    target_index = vc.get_index(vectorBucketName=NEW_VB, indexName=NEW_INDEX)["index"]
    for key in ("dataType", "dimension", "distanceMetric", "metadataConfiguration", "encryptionConfiguration"):
        if source_index.get(key) != target_index.get(key):
            raise RuntimeError(f"Vector index {key} differs")
    state.update(sync_data(s3, vc))
    for old in (SOURCE_NAMES["AfterWardDocumentProcessingDLQ"], SOURCE_NAMES["AfterWardDocumentProcessing"]):
        attrs = json.loads((CONFIG / f"{NAMES[old]}-attributes.json").read_text())
        tags = sqs.list_queue_tags(QueueUrl=sqs.get_queue_url(QueueName=old)["QueueUrl"]).get("Tags", {})
        params = dict(QueueName=NAMES[old], Attributes=attrs)
        if tags:
            params["tags"] = tags
        url = sqs.create_queue(**params)["QueueUrl"]
        state[NAMES[old]] = url
    role = iam.get_role(RoleName=OLD_ROLE)["Role"]
    kwargs = dict(RoleName=NEW_ROLE, AssumeRolePolicyDocument=json.dumps(role["AssumeRolePolicyDocument"]), Description="AfterWard document processor execution role")
    if role.get("PermissionsBoundary"):
        kwargs["PermissionsBoundary"] = role["PermissionsBoundary"]["PermissionsBoundaryArn"]
    create(iam.create_role, **kwargs)
    for page in iam.get_paginator("list_attached_role_policies").paginate(RoleName=OLD_ROLE):
        for policy in page["AttachedPolicies"]:
            iam.attach_role_policy(RoleName=NEW_ROLE, PolicyArn=policy["PolicyArn"])
    for page in iam.get_paginator("list_role_policies").paginate(RoleName=OLD_ROLE):
        for name in page["PolicyNames"]:
            document = iam.get_role_policy(RoleName=OLD_ROLE, PolicyName=name)["PolicyDocument"]
            iam.put_role_policy(RoleName=NEW_ROLE, PolicyName=replace(name), PolicyDocument=json.dumps(replace(document)))
    # Add access alongside the old index policy to retain rollback access.
    old_policy = iam.get_role_policy(RoleName="AfterWardEcsTaskRole", PolicyName="S3VectorsAccess")["PolicyDocument"]
    iam.put_role_policy(RoleName="AfterWardEcsTaskRole", PolicyName="AfterWardVectorsAccess", PolicyDocument=json.dumps(replace(old_policy)))
    function = lam.get_function(FunctionName=OLD_FUNCTION)
    cfg = function["Configuration"]
    save(BACKUP / "source-function.json", function)
    context = ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(function["Code"]["Location"], timeout=60, context=context) as download:
        code = download.read()
    kwargs = dict(FunctionName=NEW_FUNCTION, Role=f"arn:aws:iam::992617582533:role/{NEW_ROLE}", Code={"ZipFile": code})
    for key in ("Runtime", "Handler", "Timeout", "MemorySize", "Environment", "Architectures", "EphemeralStorage", "TracingConfig", "KMSKeyArn", "DeadLetterConfig", "FileSystemConfigs"):
        if cfg.get(key):
            kwargs[key] = replace(cfg[key])
    if cfg.get("SnapStart"):
        kwargs["SnapStart"] = {"ApplyOn": cfg["SnapStart"]["ApplyOn"]}
    if cfg.get("Layers"):
        kwargs["Layers"] = [layer["Arn"] for layer in cfg["Layers"]]
    if cfg.get("VpcConfig", {}).get("SubnetIds"):
        kwargs["VpcConfig"] = {k: cfg["VpcConfig"][k] for k in ("SubnetIds", "SecurityGroupIds")}
    if cfg.get("LoggingConfig"):
        kwargs["LoggingConfig"] = replace(cfg["LoggingConfig"])
    for attempt in range(12):
        try:
            create(lam.create_function, **kwargs)
            break
        except ClientError as exc:
            if "cannot be assumed" not in str(exc) or attempt == 11:
                raise
            time.sleep(5)
    lam.get_waiter("function_active_v2").wait(FunctionName=NEW_FUNCTION, WaiterConfig={"Delay": 5, "MaxAttempts": 24})
    new_cfg = lam.get_function_configuration(FunctionName=NEW_FUNCTION)
    if new_cfg["CodeSha256"] != cfg["CodeSha256"] or new_cfg["Environment"]["Variables"] != replace(cfg["Environment"]["Variables"]):
        raise RuntimeError("Replacement Lambda differs from expected code/environment")
    mappings = lam.list_event_source_mappings(FunctionName=OLD_FUNCTION)["EventSourceMappings"]
    save(BACKUP / "source-event-mappings.json", mappings)
    state["source_mapping"] = next(m for m in mappings if m["EventSourceArn"].endswith(":" + SOURCE_NAMES["AfterWardDocumentProcessing"]))
    if not lam.list_event_source_mappings(FunctionName=NEW_FUNCTION)["EventSourceMappings"]:
        mapping = state["source_mapping"]
        lam.create_event_source_mapping(FunctionName=NEW_FUNCTION, EventSourceArn=replace(mapping["EventSourceArn"]), Enabled=True, BatchSize=mapping["BatchSize"], MaximumBatchingWindowInSeconds=mapping.get("MaximumBatchingWindowInSeconds", 0), FunctionResponseTypes=mapping.get("FunctionResponseTypes", []))
    state["prepared"] = True
    save(STATE, state)
    print("AfterWard queues, role, Lambda, and trigger prepared; traffic remains on the source deployment", flush=True)


def cutover(s, state):
    if not state.get("prepared"):
        raise RuntimeError("Run prepare first")
    s3, sqs, ecs = [s.client(name) for name in ("s3", "sqs", "ecs")]
    old_url = sqs.get_queue_url(QueueName=SOURCE_NAMES["AfterWardDocumentProcessing"])["QueueUrl"]
    attrs = sqs.get_queue_attributes(QueueUrl=old_url, AttributeNames=["ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible", "ApproximateNumberOfMessagesDelayed"])["Attributes"]
    if any(int(v) for v in attrs.values()):
        raise RuntimeError("Old processing queue is not drained")
    # Synchronize before switching the MCP read path. After deployment, update
    # known upload clients and the legacy processor vector settings as documented.
    state.update(sync_data(s3, s.client("s3vectors")))
    service = ecs.describe_services(cluster="afterward-cluster", services=["afterward-mcp-service"])["services"][0]
    task = ecs.describe_task_definition(taskDefinition=service["taskDefinition"])["taskDefinition"]
    if not state.get("old_task_definition"):
        state["old_task_definition"] = service["taskDefinition"]
        save(BACKUP / "source-ecs-task.json", task)
        save(STATE, state)
    accepted = ecs.meta.service_model.operation_model("RegisterTaskDefinition").input_shape.members
    new_task = {k: v for k, v in task.items() if k in accepted}
    for container in new_task["containerDefinitions"]:
        for env in container.get("environment", []):
            if env["name"] in {"S3_VECTOR_BUCKET", "S3_VECTOR_INDEX", "DOCUMENT_BUCKET", "PROCESSING_QUEUE_URL"}:
                env["value"] = replace(env["value"])
    new_arn = ecs.register_task_definition(**new_task)["taskDefinition"]["taskDefinitionArn"]
    state["new_task_definition"] = new_arn
    save(STATE, state)
    ecs.update_service(cluster="afterward-cluster", service="afterward-mcp-service", taskDefinition=new_arn)
    print(f"ECS deployment started: {new_arn}", flush=True)
    # Install notifications after the data copy, before upload clients switch.
    config = json.loads((CONFIG / "s3-notifications.json").read_text())
    s3.put_bucket_notification_configuration(Bucket=NEW_BUCKET, NotificationConfiguration=config)
    state["notifications_enabled"] = True
    save(STATE, state)
    print("New upload notifications enabled; update local upload environment next", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["prepare", "cutover"])
    args = parser.parse_args()
    session = boto3.Session(region_name="eu-west-2")
    if session.client("sts").get_caller_identity()["Account"] != "992617582533":
        raise RuntimeError("Unexpected AWS account")
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    (prepare if args.phase == "prepare" else cutover)(session, state)


if __name__ == "__main__":
    main()
