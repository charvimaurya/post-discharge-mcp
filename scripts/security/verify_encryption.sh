#!/usr/bin/env bash
# Read-only checks that AfterWard's patient data is encrypted the way
# infra/security/README.md says. Prints PASS or FAIL per line.
#
#   scripts/security/verify_encryption.sh
#
# Every call here is a describe / get / list / head / lookup. Nothing is written,
# and the key is never disabled to "prove" anything.
# Exit code: 0 if every line passed, 1 otherwise.

set -uo pipefail

ACCOUNT=992617582533
REGION=eu-west-2
ALIAS=alias/afterward-patient-data
BUCKET=careloop-documents-992617582533-london
QUEUES=(CareLoopDocumentProcessing CareLoopDocumentProcessingDLQ)
TABLES=(PostDischargeRecoveryState PostDischargeEventHistory)
LOG_GROUPS=(/aws/lambda/CareLoopDocumentProcessor /aws/lambda/AfterwardReminderChecker)
# Who may decrypt with the key (the principals named in kms-key-policy.json).
ALLOWED="CareLoopDocumentProcessorRole AfterwardReminderRole AfterWardEcsTaskRole CareLoop"

FAILS=0
pass() { printf 'PASS  %s\n' "$*"; }
fail() { printf 'FAIL  %s\n' "$*"; FAILS=$((FAILS + 1)); }
skipped() { printf 'SKIPPED (by decision)  %s\n' "$*"; }
section() { printf '\n# %s\n' "$*"; }
# expect "label" "wanted" "got": PASS when they are equal.
expect() {
  if [[ "$3" == "$2" ]]; then pass "$1: $3"; else fail "$1: wanted $2, got ${3:-nothing}"; fi
}
# Run a read-only AWS call; print its output, or the error code if it fails.
ask() {
  local out
  if out=$("$@" 2>&1); then printf '%s' "$out"; else printf '%s' "$out" | grep -o '([A-Za-z.]*)' | head -1; fi
}

# ---------------------------------------------------------------------------
section "KMS key"
KEY_ARN=$(aws kms describe-key --region $REGION --key-id $ALIAS --query KeyMetadata.Arn --output text 2>/dev/null)
if [[ -z "$KEY_ARN" || "$KEY_ARN" == "None" ]]; then
  fail "key $ALIAS exists: not found"
  KEY_ARN="(no key)"
else
  pass "key $ALIAS exists: $KEY_ARN"
  expect "key is enabled" "Enabled" "$(ask aws kms describe-key --region $REGION --key-id $ALIAS --query KeyMetadata.KeyState --output text)"
  expect "key is customer managed" "CUSTOMER" "$(ask aws kms describe-key --region $REGION --key-id $ALIAS --query KeyMetadata.KeyManager --output text)"
  expect "yearly rotation is on" "True" "$(ask aws kms get-key-rotation-status --region $REGION --key-id "$KEY_ARN" --query KeyRotationEnabled --output text)"
fi

# ---------------------------------------------------------------------------
section "S3 letters bucket"
RULE="ServerSideEncryptionConfiguration.Rules[0]"
expect "default encryption" "aws:kms" "$(ask aws s3api get-bucket-encryption --bucket $BUCKET --region $REGION --query "$RULE.ApplyServerSideEncryptionByDefault.SSEAlgorithm" --output text)"
expect "default encryption key" "$KEY_ARN" "$(ask aws s3api get-bucket-encryption --bucket $BUCKET --region $REGION --query "$RULE.ApplyServerSideEncryptionByDefault.KMSMasterKeyID" --output text)"

# The newest uploaded letter. Letters uploaded before the key keep SSE-S3 until the lifecycle rule removes them.
LETTER=$(aws s3api list-objects-v2 --bucket $BUCKET --region $REGION --prefix patients/ \
  --query 'sort_by(Contents,&LastModified)[-1].Key' --output text 2>/dev/null)
if [[ -z "$LETTER" || "$LETTER" == "None" ]]; then
  fail "newest letter is encrypted with the key: no letter under patients/"
else
  echo "      newest letter: $LETTER"
  expect "newest letter encryption (head-object)" "aws:kms" "$(ask aws s3api head-object --bucket $BUCKET --region $REGION --key "$LETTER" --query ServerSideEncryption --output text)"
  expect "newest letter key (head-object)" "$KEY_ARN" "$(ask aws s3api head-object --bucket $BUCKET --region $REGION --key "$LETTER" --query SSEKMSKeyId --output text)"
fi

expect "lifecycle: letters under patients/ deleted after 30 days" "Enabled patients/ 30" "$(ask aws s3api get-bucket-lifecycle-configuration --bucket $BUCKET --region $REGION \
  --query "Rules[?Filter.Prefix=='patients/'] | [0].[Status,Filter.Prefix,Expiration.Days]" --output text | tr '\t' ' ')"

# ---------------------------------------------------------------------------
section "S3 access"
# A signed request over plain HTTP must be refused by the bucket policy.
out=$(aws s3api list-objects-v2 --bucket $BUCKET --region $REGION --endpoint-url http://s3.$REGION.amazonaws.com --max-items 1 2>&1)
if grep -q AccessDenied <<<"$out"; then pass "signed request over plain HTTP: AccessDenied"
else fail "signed request over plain HTTP: wanted AccessDenied, but it was allowed"; fi
# The same request over HTTPS must still work.
if aws s3api list-objects-v2 --bucket $BUCKET --region $REGION --max-items 1 >/dev/null 2>&1; then pass "signed request over HTTPS: allowed"
else fail "signed request over HTTPS: refused"; fi
# An anonymous public URL for a real letter must be refused.
URL="https://$BUCKET.s3.$REGION.amazonaws.com/${LETTER:-patients/}"
body=$(curl -s -w '\n%{http_code}' "$URL")
code=${body##*$'\n'}
if [[ "$code" == 403 ]] && grep -q AccessDenied <<<"$body"; then pass "anonymous public URL: 403 AccessDenied"
else fail "anonymous public URL: wanted 403 AccessDenied, got HTTP $code"; fi
expect "all four public-access blocks" "True True True True" "$(ask aws s3api get-public-access-block --bucket $BUCKET --region $REGION \
  --query 'PublicAccessBlockConfiguration.[BlockPublicAcls,IgnorePublicAcls,BlockPublicPolicy,RestrictPublicBuckets]' --output text | tr '\t' ' ')"

# ---------------------------------------------------------------------------
section "DynamoDB tables"
for table in "${TABLES[@]}"; do
  expect "$table encryption" "ENABLED KMS" "$(ask aws dynamodb describe-table --region $REGION --table-name $table --query 'Table.SSEDescription.[Status,SSEType]' --output text | tr '\t' ' ')"
  expect "$table key" "$KEY_ARN" "$(ask aws dynamodb describe-table --region $REGION --table-name $table --query Table.SSEDescription.KMSMasterKeyArn --output text)"
  expect "$table point-in-time recovery" "ENABLED" "$(ask aws dynamodb describe-continuous-backups --region $REGION --table-name $table --query ContinuousBackupsDescription.PointInTimeRecoveryDescription.PointInTimeRecoveryStatus --output text)"
  expect "$table deletion protection" "True" "$(ask aws dynamodb describe-table --region $REGION --table-name $table --query Table.DeletionProtectionEnabled --output text)"
done

# ---------------------------------------------------------------------------
section "SQS queues"
for queue in "${QUEUES[@]}"; do
  url=https://sqs.$REGION.amazonaws.com/$ACCOUNT/$queue
  expect "$queue key" "$KEY_ARN" "$(ask aws sqs get-queue-attributes --region $REGION --queue-url $url --attribute-names KmsMasterKeyId --query Attributes.KmsMasterKeyId --output text)"
done

# ---------------------------------------------------------------------------
section "Lambda log groups"
for group in "${LOG_GROUPS[@]}"; do
  # Left on CloudWatch's default encryption: the logs hold ids, counts and error types only.
  skipped "$group encrypted with the key"
  expect "$group retention (days)" "30" "$(ask aws logs describe-log-groups --region $REGION --log-group-name-prefix $group --query "logGroups[?logGroupName=='$group'].retentionInDays | [0]" --output text)"
done

# ---------------------------------------------------------------------------
section "Who decrypted with the key (last 10 CloudTrail Decrypt events)"
if [[ "$KEY_ARN" == "(no key)" ]]; then
  fail "CloudTrail Decrypt events: there is no key to look up"
else
  events=$(aws cloudtrail lookup-events --region $REGION --max-results 50 \
    --lookup-attributes AttributeKey=ResourceName,AttributeValue="$KEY_ARN" --output json 2>&1)
  if [[ $? -ne 0 ]]; then
    fail "CloudTrail Decrypt events: could not read CloudTrail $(grep -o '([A-Za-z.]*)' <<<"$events" | head -1)"
  else
    # One line per event: PASS when the caller is a principal the key policy names, or an AWS service acting for one.
    ALLOWED="$ALLOWED" python3 -c '
import json, os, sys
allowed = set(os.environ["ALLOWED"].split())
rows = []
for event in json.load(sys.stdin).get("Events", []):
    detail = json.loads(event["CloudTrailEvent"])
    if detail.get("eventName") != "Decrypt":
        continue
    who = detail.get("userIdentity", {})
    name = (who.get("sessionContext", {}).get("sessionIssuer", {}).get("userName")
            or who.get("userName") or who.get("invokedBy") or who.get("type") or "unknown")
    via = who.get("invokedBy") or detail.get("sourceIPAddress", "")
    ok = name in allowed or name.endswith(".amazonaws.com")
    rows.append((ok, detail.get("eventTime", ""), name, via))
if not rows:
    print("FAIL  no Decrypt events for the key yet (CloudTrail can be 15 minutes behind)")
for ok, when, name, via in rows[:10]:
    print("%s  %s  Decrypt by %s  via %s" % ("PASS" if ok else "FAIL", when, name, via))
sys.exit(0 if rows and all(row[0] for row in rows[:10]) else 1)
' <<<"$events" || FAILS=$((FAILS + 1))
  fi
fi

# ---------------------------------------------------------------------------
if [[ $FAILS -eq 0 ]]; then printf '\nAll checks passed.\n'; else printf '\n%d check(s) failed.\n' "$FAILS"; fi
[[ $FAILS -eq 0 ]]
