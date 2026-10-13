"""Grant the reviewed migration access and rename the existing deployment user."""

import json
from pathlib import Path

import boto3


IDENTITY = json.loads(Path("deployment/name-migration/resource-names.json").read_text())["identity"]
SOURCE_USER = IDENTITY["source_name"]
TARGET_USER = IDENTITY["target_name"]

def main():
    session = boto3.Session(region_name="eu-west-2")
    identity = session.client("sts").get_caller_identity()
    if identity["Arn"] != f"arn:aws:iam::992617582533:user/{SOURCE_USER}":
        raise RuntimeError("Expected the original deployment identity")
    iam = session.client("iam")
    user = iam.get_user(UserName=SOURCE_USER)["User"]
    try:
        iam.get_user(UserName=TARGET_USER)
    except iam.exceptions.NoSuchEntityException:
        pass
    else:
        raise RuntimeError("AfterWard already exists; do not overwrite it")
    # Policies naming the old user as a Resource are not rewritten by IAM.
    # Detect those before renaming rather than silently losing self-access.
    policies = []
    for page in iam.get_paginator("list_user_policies").paginate(UserName=SOURCE_USER):
        for name in page["PolicyNames"]:
            policies.append(iam.get_user_policy(UserName=SOURCE_USER, PolicyName=name)["PolicyDocument"])
    groups = []
    for page in iam.get_paginator("list_groups_for_user").paginate(UserName=SOURCE_USER):
        groups.extend(group["GroupName"] for group in page["Groups"])
    attached = []
    for page in iam.get_paginator("list_attached_user_policies").paginate(UserName=SOURCE_USER):
        attached.extend(page["AttachedPolicies"])
    for group in groups:
        for page in iam.get_paginator("list_group_policies").paginate(GroupName=group):
            for name in page["PolicyNames"]:
                policies.append(iam.get_group_policy(GroupName=group, PolicyName=name)["PolicyDocument"])
        for page in iam.get_paginator("list_attached_group_policies").paginate(GroupName=group):
            attached.extend(page["AttachedPolicies"])
    for policy in attached:
        version = iam.get_policy(PolicyArn=policy["PolicyArn"])["Policy"]["DefaultVersionId"]
        policies.append(iam.get_policy_version(PolicyArn=policy["PolicyArn"], VersionId=version)["PolicyVersion"]["Document"])
    for policy in policies:
        for statement in policy.get("Statement", []):
            for key in ("Resource", "NotResource", "Condition"):
                if f"user/{SOURCE_USER}" in json.dumps(statement.get(key, "")):
                    raise RuntimeError("A policy references the old user outside Principal; review it before renaming")
    policy = Path("deployment/name-migration/required-additional-access.json").read_text()
    # The existing user's combined inline policies already fill its 2 KB quota.
    policy_arn = "arn:aws:iam::992617582533:policy/AfterWardNameMigration"
    try:
        iam.create_policy(PolicyName="AfterWardNameMigration", PolicyDocument=policy,
                          Description="Scoped access for migrating original resources to AfterWard")
    except iam.exceptions.EntityAlreadyExistsException:
        existing = iam.get_policy(PolicyArn=policy_arn)["Policy"]
        document = iam.get_policy_version(PolicyArn=policy_arn, VersionId=existing["DefaultVersionId"])["PolicyVersion"]["Document"]
        if document != json.loads(policy):
            raise RuntimeError("Existing migration policy differs; review before attaching")
    iam.attach_user_policy(UserName=SOURCE_USER, PolicyArn=policy_arn)
    print("Attached AfterWardNameMigration access policy", flush=True)
    iam.update_user(UserName=SOURCE_USER, NewUserName=TARGET_USER)
    renamed = iam.get_user(UserName=TARGET_USER)["User"]
    if renamed["UserId"] != user["UserId"]:
        raise RuntimeError("User identity changed unexpectedly")
    print("Renamed the deployment user to AfterWard; unique user ID preserved", flush=True)
    print("Current credential identity:", session.client("sts").get_caller_identity()["Arn"], flush=True)


if __name__ == "__main__":
    main()
