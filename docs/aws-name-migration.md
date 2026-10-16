# Migrating CareLoop resource names to AfterWard

## Current status

Live resources were inspected in account `<ACCOUNT_ID>`, region `eu-west-2`, on 13 October 2026. The migration is complete. Active uploads and MCP search use the AfterWard replacements in [deployment/name-migration](../deployment/name-migration/resource-names.json). The original resources are retained for rollback.

The initial inventory used the IAM user `CareLoop`, subsequently renamed to `AfterWard`. IAM permission simulation reports `implicitDeny` for `s3:CreateBucket`. Actual inventory calls also returned access denied for `ecs:ListServices` and `sqs:ListQueueTags`. The scoped permissions were subsequently granted through the managed policy `AfterWardNameMigration`. A fresh inventory succeeded for ECS services and queue tags, and simulation confirmed permission to create the proposed London bucket. The [additional-access policy](../deployment/name-migration/required-additional-access.json) scopes bucket creation to the proposed London bucket; it does not grant permission to delete resources. Permission simulation is a preflight check, not a guarantee that every API call will succeed.

Private snapshots are saved under the ignored directory `infra/security/backup/name-migration/20261013T144631Z/`, with restricted file permissions. They include live function configuration and a temporary code-download URL; do not commit them. Rerun `python -m scripts.deployment.inventory_aws_names` before executing the migration because settings and data may have changed.

## Confirmed source configuration

- The letters bucket has 124 objects totaling 1,329,490 bytes and no enabled versioning.
- The letter bucket uses SSE-S3 (`AES256`), not the custom KMS configuration proposed elsewhere in the repository.
- Both SQS queues are empty, use managed SQS encryption, and retain messages for four days. The processing queue has a 180-second visibility timeout and sends messages to its dead-letter queue after three receives.
- The document Lambda uses Python 3.11 on x86_64, 1,024 MB memory, and a 120-second timeout. Its queue mapping uses batch size one and `ReportBatchItemFailures`.
- The vector index uses 512-dimensional float32 vectors, cosine distance, and non-filterable `text` and `section` metadata. Its bucket and index use `AES256` encryption.
- The `alias/afterward-patient-data` KMS alias was not found. Do not apply the proposed custom-key policy as part of this rename.
- The `afterward-cluster` ECS cluster and `afterward-mcp-service` service exist. Their live service and task settings were saved in the refreshed inventory `infra/security/backup/name-migration/20261013T145420Z/`.
- The reminder function and `afterward-reminder-checker` schedule exist and their settings were saved.


## Completed migration and checks

- Created the replacement letters bucket, vector bucket/index, processing/dead-letter queues, execution role, and document Lambda in London.
- Verified the initial 124 copied letter objects by content hash and all 640 vectors by values and metadata. One additional ready document and seven vectors arrived during migration and were synchronized afterward; all source object keys are present in the destination.
- The copied index preserves the best result in a representative search; independently built approximate indexes can differ in lower-ranked results.
- Enabled the new bucket notification with the lowercase `prefix` filter required for matching `patients/`. The source snapshot used `Prefix`, which did not deliver the synthetic object event when copied unchanged.
- ECS service `afterward-mcp-service` completed deployment of task revision `afterward-mcp:5` and has one running task.
- Updated active repository settings, `.env`, and `web/.env.local`; restarted the local web bridge. Private environment backups are in the ignored snapshot directory.
- Kept older upload clients compatible by changing only the legacy document Lambda's vector bucket/index to the AfterWard index. Its original environment is saved in `infra/security/backup/name-migration/legacy-lambda-environment.json`; restore it when rolling back that path.
- A synthetic fixture under patient `migration_check_20261013` reached a ready plan through the new S3 → SQS → Lambda path and produced four chunks in the new vector index. That isolated test object, plan, and vectors remain available as verification evidence; the demo patient's plan was not replaced by this test.
- Deployed MCP plan/task/medicine reads and letter search passed. The restarted bridge returned HTTP 200 for Today and an agent answer containing letter evidence. The reminder Lambda succeeded for the isolated patient and its schedule remains enabled.
- The relevant ingestion, MCP, and reminder tests passed: 29 tests, with two deselected by the existing test configuration.

## Resource names

| Existing | Replacement |
| --- | --- |
| `careloop-documents-<ACCOUNT_ID>-london` | `afterward-documents-<ACCOUNT_ID>-london` |
| `careloop-vectors-<ACCOUNT_ID>-london` | `afterward-vectors-<ACCOUNT_ID>-london` |
| `careloop-discharge-index` | `afterward-discharge-index` |
| `CareLoopDocumentProcessing` | `AfterWardDocumentProcessing` |
| `CareLoopDocumentProcessingDLQ` | `AfterWardDocumentProcessingDLQ` |
| `CareLoopDocumentProcessor` | `AfterWardDocumentProcessor` |
| `CareLoopDocumentProcessorRole` | `AfterWardDocumentProcessorRole` |

The existing IAM user was renamed from `CareLoop` to `AfterWard` on 13 October 2026, preserving its unique ID, access keys, group memberships, and attached permissions. Console sign-in now uses `AfterWard`. DynamoDB tables, reminder resources, MCP authentication, and existing public endpoints are preserved.

## Execution order

1. Resolve the permission blocker and refresh the inventory. Inspect the live ECS service, current task revision, both source role policies, and all upload clients. Identify the environment files used by the web upload route and local bridge without printing their secrets.
2. Create the new letter bucket in London. Apply the prepared encryption, public-access block, lifecycle, and HTTPS bucket policy, matching the live settings. Leave upload notifications unset while copying objects, so historical letters do not trigger processing. Verify object counts, keys, sizes, and contents after copying.
3. Create the vector bucket with matching encryption and index mode, then create the prepared index. Page through the source index with vector data and metadata included, write bounded batches to the destination, and verify every copied key and value. Do not call Bedrock again when the existing embeddings can be copied. Confirm search results match the source for a representative patient and document.
4. Create the new dead-letter queue first, then the processing queue using the prepared attributes. The prepared processing queue policy authorizes only the new letters bucket to send S3 events. Preserve source queue tags once they can be inspected.
5. Create the new Lambda execution role using the source trust policy. Copy the live inline policies with old resource references replaced, and retain its attached logging policy. Inspect source permissions before choosing the final policy; the repository's stricter policy differs from the live setup. Add new storage/index access to the existing MCP role alongside its existing access so rollback still works.
6. Clone the live Lambda code and operational settings into `AfterWardDocumentProcessor`, replacing only the role, letter bucket, and vector names. Obtain a fresh code-download URL when needed. Wait for the function to become active, then create its SQS mapping with the source batch and response settings.
7. Pause uploads for the cutover, wait for the old queue to drain, and repeat the object/vector comparison to catch changes since the initial copy. Configure the new bucket's S3 notification only after copies finish. Historical copied objects must not generate new ingestion events.
8. Register a new ECS task revision derived from the actual deployed revision, changing only the vector bucket/index settings, and deploy it to the confirmed MCP service. Update web and local upload/processing settings to the new bucket and queue. Preserve task secrets, image digest, networking, ports, and endpoint settings. Restart affected local processes after environment changes, then resume uploads.
9. Upload a new synthetic letter and verify S3 → new SQS → new Lambda → DynamoDB ready state → new vector index. Test MCP tool listing, letter search, agent answers, completion tracking, and scheduled reminders. Inspect failures and dead-letter queues. Never log letter contents or token values during verification.
10. Promote the verified names into active repository configuration, deployment instructions, security scripts, environment examples, and architecture documentation. The active callers use `DOCUMENT_BUCKET`; the old bucket environment fallback was removed after the migration. Run the ingestion, RAG, MCP, and reminder checks appropriate to the final changes.

## Rollback

Keep the original bucket, queues, vector index, Lambda, role, and ECS task revision. If verification fails, pause uploads, drain or account for messages already accepted by the new queue, restore the previous ECS revision and upload environment, and resume the old upload path. Reconcile letters and vectors created after cutover before restoring the old search configuration; otherwise those documents may be missing from search. Do not replay old messages blindly because processing writes the shared recovery plan. DynamoDB changes made during the migration are not undone by reverting resource names.

## Retirement

Deletion is a separate step requiring explicit approval after the migration has been verified. Keep the old deployment available for rollback until then. No deletion commands are included in this preparation.
