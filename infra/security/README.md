# Storage security for AfterWard

The demo uses synthetic data, but storage is set up the way real health data
should be. Everything here is applied by `scripts/security/harden_storage.sh`,
which only prints the commands unless run with `--apply`.

| File | What it sets |
|---|---|
| `kms-key-policy.json` | One customer-managed key. Only the two Lambda roles, the MCP server's ECS task role and the `CareLoop` user may use it, and only through S3, DynamoDB or SQS in eu-west-2. S3 may use it to post upload events to the encrypted queue; CloudWatch Logs may use it for the two Lambda log groups. |
| `s3-encryption.json` | Letters bucket: SSE-KMS with that key, S3 Bucket Key on (fewer KMS calls), SSE-C blocked. |
| `s3-bucket-policy.json` | Deny any request not over HTTPS, and any below TLS 1.2. |
| `s3-public-access-block.json` | All four public-access blocks on (already on today). |
| `s3-lifecycle.json` | Delete uploaded letters (`patients/`) 30 days after upload. |
| `iam-document-processor-policy.json` | Document Lambda: one scoped policy. Replaces two overlapping ones that used `Resource: "*"` for S3 Vectors and Bedrock. |
| `iam-ecs-task-policy.json` | MCP server: one scoped policy. Replaces S3, DynamoDB, Bedrock and Secrets Manager full access and two unused QuickSight policies. |

## Order

1. Key and key policy. 2. S3. 3. SQS. 4. DynamoDB. 5. Logs. 6. IAM. 7. Read-only check.

The key policy names each role, so no IAM policy needs KMS permissions.

## After applying, check

- Upload a letter from `/demo`: it should reach `ready` (S3 → SQS → Lambda all use the key).
- Chat on `/demo` and run the reminder check: DynamoDB reads and writes still work.
- The deployed MCP server still answers `tools/list` and `get_today_tasks`.

## Undo

| Step | Undo |
|---|---|
| S3 encryption | `aws s3api put-bucket-encryption` with `"SSEAlgorithm": "AES256"` |
| Bucket policy | `aws s3api delete-bucket-policy --bucket careloop-documents-992617582533-london` |
| Lifecycle | `aws s3api delete-bucket-lifecycle --bucket careloop-documents-992617582533-london` (letters already deleted cannot come back) |
| SQS | `aws sqs set-queue-attributes ... --attributes KmsMasterKeyId=""` then `SqsManagedSseEnabled=true` |
| DynamoDB | `aws dynamodb update-table ... --sse-specification Enabled=false` (back to the AWS-owned key) |
| IAM | Re-attach the managed policies listed in the script; restore the old inline policies from `deployment/` or the script's earlier versions |
| Key | Never delete it while anything is encrypted with it. Schedule deletion (7–30 days) only after every step above is undone. |

## Not covered here

- **S3 Vectors** (`careloop-vectors-…`) stores letter text as metadata, encrypted with
  SSE-S3 (AES256). The encryption type is fixed when a vector bucket is created, so
  moving to the KMS key means a new vector bucket and index created with
  `--encryption-configuration sseType=aws:kms,kmsKeyArn=<key>`, re-indexing the
  letters, and pointing `S3_VECTOR_BUCKET` at it.
- **Letters already uploaded** keep SSE-S3 until the 30-day rule deletes them.
  Copying them in place to re-encrypt would raise new upload events and re-read old
  letters into the current plan.
- **What else is kept**: the 30-day rule deletes the uploaded PDF only. The plan
  (DynamoDB), Event History and the search index keep their copies of the letter's
  content; set their retention separately.
- **The `CareLoop` IAM user** has `IAMFullAccess` and several full-access policies.
  Use it for setup only and give the running app its own narrow role.
