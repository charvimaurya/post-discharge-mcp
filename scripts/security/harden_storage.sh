#!/usr/bin/env bash
# Harden how AfterWard stores patient data, in rounds.
#
# By default this only PRINTS the commands. Nothing changes until --apply.
#
#   scripts/security/harden_storage.sh --round 1            # show round 1
#   scripts/security/harden_storage.sh --round 1 --apply    # run round 1 (asks once)
#   scripts/security/harden_storage.sh --round 2 --only sqs --apply   # one service of round 2: kms | s3 | sqs | dynamodb
#   scripts/security/harden_storage.sh --undo-sqs --apply   # queues back to SQS-managed encryption
#
# Round 1: S3 HTTPS-only bucket policy, S3 30-day lifecycle, log retention 30 days,
#          DynamoDB point-in-time recovery + deletion protection.
# Round 2: KMS key + alias + rotation; S3, SQS and DynamoDB encryption with it.
#          (Log groups are left on CloudWatch's default encryption, by decision.)
# Round 3: IAM least privilege (run after the demo video).
#
# Each round ends with read-only checks. A backup of the settings before any change
# is in infra/security/backup/.
#
# Not done here (see infra/security/README.md): S3 Vectors encryption (fixed at
# creation) and re-encrypting letters already in S3 (copying in place re-processes them).

set -euo pipefail

ACCOUNT=992617582533
REGION=eu-west-2
ALIAS=alias/afterward-patient-data
BUCKET=careloop-documents-992617582533-london
QUEUE_URLS=(
  https://sqs.eu-west-2.amazonaws.com/${ACCOUNT}/CareLoopDocumentProcessing
  https://sqs.eu-west-2.amazonaws.com/${ACCOUNT}/CareLoopDocumentProcessingDLQ
)
TABLES=(PostDischargeRecoveryState PostDischargeEventHistory)
LOG_GROUPS=(/aws/lambda/CareLoopDocumentProcessor /aws/lambda/AfterwardReminderChecker)
DOC_ROLE=CareLoopDocumentProcessorRole
REMINDER_ROLE=AfterwardReminderRole
ECS_TASK_ROLE=AfterWardEcsTaskRole
HERE="$(cd "$(dirname "$0")/../.." && pwd)/infra/security"

APPLY=false
ROUND=""
UNDO_SQS=false
ONLY=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) APPLY=true ;;
    --round) ROUND="${2:-}"; shift ;;
    --undo-sqs) UNDO_SQS=true ;;
    --only) ONLY="${2:-}"; shift ;;
    *) echo "Unknown option: $1"; exit 2 ;;
  esac
  shift
done

if ! $UNDO_SQS && [[ ! "$ROUND" =~ ^[123]$ ]]; then
  echo "Choose a round: --round 1, --round 2 or --round 3 (or --undo-sqs)."
  exit 2
fi

run() {
  printf '  %s\n' "$*"
  if $APPLY; then eval "$@"; fi
}

check() {
  printf '  %s\n' "$*"
  eval "$@" || true
}

section() { printf '\n# %s\n' "$*"; }

# Round 2 can run one service at a time: --only kms | s3 | sqs | dynamodb
want() { [[ -z "$ONLY" || "$ONLY" == "$1" ]]; }

key_arn() {
  aws kms describe-key --key-id "$ALIAS" --region "$REGION" --query KeyMetadata.Arn --output text 2>/dev/null || true
}

if $APPLY; then
  what=$($UNDO_SQS && echo "undo the SQS encryption step" || echo "apply round $ROUND")
  read -r -p "This will ${what} in AWS account ${ACCOUNT} (${REGION}). Type 'apply' to continue: " answer
  [[ "$answer" == "apply" ]] || { echo "Nothing changed."; exit 1; }
fi

# ---------------------------------------------------------------------------
if $UNDO_SQS; then
  section "Undo: queues back to SQS-managed encryption"
  for url in "${QUEUE_URLS[@]}"; do
    run "aws sqs set-queue-attributes --region $REGION --queue-url $url --attributes KmsMasterKeyId=\"\",SqsManagedSseEnabled=true"
  done
  section "Check (read-only)"
  for url in "${QUEUE_URLS[@]}"; do
    check "aws sqs get-queue-attributes --region $REGION --queue-url $url --attribute-names SqsManagedSseEnabled KmsMasterKeyId --output text"
  done
  exit 0
fi

# ---------------------------------------------------------------------------
if [[ "$ROUND" == 1 ]]; then
  section "Round 1a. S3: HTTPS-only bucket policy, 30-day lifecycle"
  run "aws s3api put-bucket-policy --bucket $BUCKET --region $REGION --policy file://$HERE/s3-bucket-policy.json"
  run "aws s3api put-bucket-lifecycle-configuration --bucket $BUCKET --region $REGION --lifecycle-configuration file://$HERE/s3-lifecycle.json"

  section "Round 1b. Lambda logs: keep 30 days"
  for group in "${LOG_GROUPS[@]}"; do
    run "aws logs put-retention-policy --region $REGION --log-group-name $group --retention-in-days 30"
  done

  section "Round 1c. DynamoDB: point-in-time recovery and deletion protection"
  for table in "${TABLES[@]}"; do
    run "aws dynamodb update-continuous-backups --region $REGION --table-name $table --point-in-time-recovery-specification PointInTimeRecoveryEnabled=true"
    run "aws dynamodb update-table --region $REGION --table-name $table --deletion-protection-enabled --query TableDescription.DeletionProtectionEnabled --output text"
  done

  section "Round 1 checks (read-only)"
  check "aws s3api get-bucket-policy --bucket $BUCKET --region $REGION --query Policy --output text"
  check "aws s3api get-bucket-lifecycle-configuration --bucket $BUCKET --region $REGION --query 'Rules[].[ID,Status,Expiration.Days]' --output text"
  echo "  # Signed request over plain HTTP: allowed before round 1, AccessDenied after."
  check "aws s3api list-objects-v2 --bucket $BUCKET --region $REGION --endpoint-url http://s3.$REGION.amazonaws.com --max-items 1 --query KeyCount --output text"
  echo "  # Same request over HTTPS: must still work."
  check "aws s3api list-objects-v2 --bucket $BUCKET --region $REGION --max-items 1 --query KeyCount --output text"
  for group in "${LOG_GROUPS[@]}"; do
    check "aws logs describe-log-groups --region $REGION --log-group-name-prefix $group --query 'logGroups[].[logGroupName,retentionInDays]' --output text"
  done
  for table in "${TABLES[@]}"; do
    check "aws dynamodb describe-continuous-backups --region $REGION --table-name $table --query 'ContinuousBackupsDescription.PointInTimeRecoveryDescription.PointInTimeRecoveryStatus' --output text"
    check "aws dynamodb describe-table --region $REGION --table-name $table --query 'Table.DeletionProtectionEnabled' --output text"
  done
fi

# ---------------------------------------------------------------------------
if [[ "$ROUND" == 2 ]]; then
  KEY_ARN=$(key_arn)
  [[ "$KEY_ARN" == "None" ]] && KEY_ARN=""

  if want kms; then
    section "Round 2a. KMS key, alias, yearly rotation"
    if [[ -z "$KEY_ARN" ]]; then
      run "KEY_ARN=\$(aws kms create-key --region $REGION --description 'AfterWard patient data (S3, DynamoDB, SQS)' --key-usage ENCRYPT_DECRYPT --key-spec SYMMETRIC_DEFAULT --policy file://$HERE/kms-key-policy.json --query KeyMetadata.Arn --output text)"
      run "aws kms create-alias --region $REGION --alias-name $ALIAS --target-key-id \"\$KEY_ARN\""
    else
      echo "  (key already exists: $KEY_ARN; its policy is refreshed)"
      run "aws kms put-key-policy --region $REGION --key-id $KEY_ARN --policy-name default --policy file://$HERE/kms-key-policy.json"
    fi
    run "aws kms enable-key-rotation --region $REGION --key-id \"\$KEY_ARN\""
    check "aws kms describe-key --region $REGION --key-id $ALIAS --query 'KeyMetadata.[Arn,KeyState]' --output text"
    check "aws kms get-key-rotation-status --region $REGION --key-id \"\$KEY_ARN\" --query KeyRotationEnabled --output text"
  fi

  if [[ -z "$KEY_ARN" ]]; then
    if $APPLY || ! want kms; then echo "The key $ALIAS does not exist yet. Run --round 2 --only kms first."; exit 1; fi
    KEY_ARN='<new key ARN>'
  fi

  if want s3; then
    section "Round 2b. S3 letters bucket: SSE-KMS with the key"
    TMP=$(mktemp -d)
    sed "s|{{KMS_KEY_ARN}}|${KEY_ARN}|g" "$HERE/s3-encryption.json" > "$TMP/s3-encryption.json"
    run "aws s3api put-bucket-encryption --bucket $BUCKET --region $REGION --server-side-encryption-configuration file://$TMP/s3-encryption.json"
    rm -rf "$TMP"
    check "aws s3api get-bucket-encryption --bucket $BUCKET --region $REGION --query 'ServerSideEncryptionConfiguration.Rules[0].ApplyServerSideEncryptionByDefault' --output text"
  fi

  if want sqs; then
    section "Round 2c. SQS queues: SSE-KMS with the key (undo: --undo-sqs)"
    for url in "${QUEUE_URLS[@]}"; do
      run "aws sqs set-queue-attributes --region $REGION --queue-url $url --attributes KmsMasterKeyId=$KEY_ARN,KmsDataKeyReusePeriodSeconds=300"
      check "aws sqs get-queue-attributes --region $REGION --queue-url $url --attribute-names KmsMasterKeyId --query Attributes.KmsMasterKeyId --output text"
    done
  fi

  if want dynamodb; then
    section "Round 2d. DynamoDB tables: SSE-KMS with the key"
    for table in "${TABLES[@]}"; do
      run "aws dynamodb update-table --region $REGION --table-name $table --sse-specification Enabled=true,SSEType=KMS,KMSMasterKeyId=$KEY_ARN --query TableDescription.SSEDescription.Status --output text"
      check "aws dynamodb describe-table --region $REGION --table-name $table --query 'Table.[TableStatus,SSEDescription.Status,SSEDescription.SSEType]' --output text"
    done
  fi

  # Not done, by decision: encrypting the Lambda log groups with the key. Logs are
  # encrypted by CloudWatch by default and hold ids, counts and error types only.
fi

# ---------------------------------------------------------------------------
if [[ "$ROUND" == 3 ]]; then
  section "Round 3a. Document Lambda: one scoped policy (no Resource \"*\")"
  run "aws iam put-role-policy --role-name $DOC_ROLE --policy-name AfterwardDocumentProcessor --policy-document file://$HERE/iam-document-processor-policy.json"
  run "aws iam delete-role-policy --role-name $DOC_ROLE --policy-name CareLoopDocumentProcessorRole"
  run "aws iam delete-role-policy --role-name $DOC_ROLE --policy-name CareLoopDocumentProcessorRolePolicy"

  section "Round 3b. Reminder Lambda: drop the redundant logging policy"
  run "aws iam delete-role-policy --role-name $REMINDER_ROLE --policy-name AfterwardReminderLogging"

  section "Round 3c. MCP server (ECS task role): one scoped policy replaces seven broad ones"
  run "aws iam put-role-policy --role-name $ECS_TASK_ROLE --policy-name AfterwardMcpServer --policy-document file://$HERE/iam-ecs-task-policy.json"
  for managed in SecretsManagerReadWrite AmazonDynamoDBFullAccess AmazonS3FullAccess AmazonBedrockFullAccess \
                 AWSSecretsManagerClientReadOnlyAccess service-role/AWSQuickSightSecretsManagerWriteAccess \
                 AWSQuickSightSecretsManagerWritePolicy; do
    run "aws iam detach-role-policy --role-name $ECS_TASK_ROLE --policy-arn arn:aws:iam::aws:policy/$managed"
  done

  section "Round 3 checks (read-only)"
  for role in $DOC_ROLE $REMINDER_ROLE $ECS_TASK_ROLE; do
    check "aws iam list-role-policies --role-name $role --query PolicyNames --output text"
    check "aws iam list-attached-role-policies --role-name $role --query 'AttachedPolicies[].PolicyName' --output text"
  done
fi

$APPLY || printf '\nDry run only. Nothing was changed. Add --apply to run this round.\n'
