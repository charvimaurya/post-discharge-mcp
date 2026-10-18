# AWS integrations

AfterWard runs on AWS in the London region (eu-west-2). Amazon Bedrock reads each
discharge letter into a recovery plan and runs the assistant; the plan lives in
DynamoDB, the letter's text is searchable in S3 Vectors, and a self-hosted MCP
server on ECS Fargate gives the assistant its tools.

**How this page was checked (18 October 2026).** Every row was traced to the code
that calls the service and the file that defines its deployment. "Live" means a
read-only AWS describe/get call on 18 October 2026 found the resource in the state
shown. No model was called, no secret value or patient record was read, and nothing
was created, changed or deployed.

## Services

| Service | What it does in AfterWard | Source code | Deployment definition | Status (18 Oct, read-only) |
| --- | --- | --- | --- | --- |
| Amazon Bedrock: Claude (Converse API) | Turns letter text into a structured plan; runs the assistant that answers and records progress | [bedrock.py](../app/ingestion/bedrock.py) (`converse`), [agent service](../app/agent/service.py) | Model IDs in [.env.example](../.env.example) and [lambda-env.json](../deployment/lambda-env.json) | Called by the live document Lambda and the bridge. No model call made in this check |
| Amazon Bedrock: image model | Reads photos and handwritten letters | [image_processor.py](../app/ingestion/image_processor.py) (`converse`) | `IMAGE_MODEL_ID` in [.env.example](../.env.example) | In code; not exercised in this check |
| Amazon Titan Text Embeddings V2 | Turns letter passages and questions into 512-number vectors for search | [embeddings.py](../app/rag/embeddings.py) (`invoke_model`), default `amazon.titan-embed-text-v2:0` in [config.py](../app/config.py) | `EMBEDDING_MODEL_ID`, `EMBEDDING_DIMENSIONS` in [lambda-env.json](../deployment/lambda-env.json) | Live index dimension (512) matches. No call made |
| Amazon S3 | Stores uploaded letters; each new letter starts processing | [s3_service.py](../app/aws/s3_service.py), [upload route](../web/app/api/upload/route.ts), [web/lib/aws.ts](../web/lib/aws.ts) | [s3-notifications.json](../deployment/name-migration/s3-notifications.json), [infra/security](../infra/security/README.md) | **Live.** Bucket encryption SSE-S3 (AES256); `s3:ObjectCreated:*` notifies the processing queue |
| Amazon S3 Vectors | Searches the letter's own sentences, filtered to one patient and the current letter | [vector_store.py](../app/rag/vector_store.py), [rag/service.py](../app/rag/service.py) | [vector-index.json](../deployment/name-migration/vector-index.json) | **Live.** Index `afterward-discharge-index`, 512 dimensions, cosine |
| Amazon SQS, with dead-letter queue | Queues each upload for processing; a letter that fails 3 times moves to the dead-letter queue | [document_processor handler](../lambdas/document_processor/handler.py); [sqs_service.py](../app/aws/sqs_service.py) is used by the diagnostic scripts in `scripts/aws/` | [redrive-policy.json](../deployment/redrive-policy.json) | **Live.** `maxReceiveCount` 3 to `AfterWardDocumentProcessingDLQ`; SQS-managed encryption on |
| AWS Lambda | `AfterWardDocumentProcessor` turns a letter into a plan; `AfterwardReminderChecker` decides when AfterWard should speak first | [document_processor](../lambdas/document_processor/handler.py), [reminder_checker](../lambdas/reminder_checker/handler.py) | [build_document_lambda.py](../scripts/deployment/build_document_lambda.py), [deployment README](../deployment/README.md) | **Live.** Both Active, Python 3.11. Code last updated 14 Oct and 9 Oct; later repo changes are not deployed |
| Amazon DynamoDB | `PostDischargeRecoveryState` holds the plan and reminder state; `PostDischargeEventHistory` holds what was done and when | [recovery_state.py](../app/database/recovery_state.py), [event_history.py](../app/database/event_history.py) | [AWS setup](aws-setup.md) | **Live.** Both tables ACTIVE |
| Amazon EventBridge Scheduler | Runs the reminder check every 5 minutes | Invokes the reminder Lambda | [reminder-schedule-target.json](../deployment/reminder-schedule-target.json), [scheduler policies](../deployment/scheduler-invoke-policy.json), [deployment README](../deployment/README.md) | **Live.** `afterward-reminder-checker`, `rate(5 minutes)`, ENABLED |
| Amazon ECS on Fargate, Amazon ECR | Hosts the MCP server | [MCP HTTP server](../app/mcp/http_server.py), [Dockerfile](../Dockerfile) | [ecs-task-definition.json](../ecs-task-definition.json) | **Live.** `afterward-mcp-service` ACTIVE, 1 running task, task definition `afterward-mcp:6` (registered 18 Oct; adds CloudWatch logging only), image `afterward-mcp:latest` from ECR, pushed 8 Oct |
| Elastic Load Balancing | Routes traffic from CloudFront to the MCP containers | n/a | [ecs-task-definition.json](../ecs-task-definition.json) (`ALB_HOST`) | **Live.** `afterward-mcp-alb`, application, internet-facing, active |
| Amazon CloudFront | HTTPS front door for the MCP server | n/a | [cloudfront-config.json](../cloudfront-config.json) | **Live.** Two distributions Deployed and enabled, both with the ALB as origin. One uses HTTPS to the origin, one HTTP |
| AWS Secrets Manager | Holds the MCP bearer token, so it is never in code or task settings | [mcp_auth.py](../app/auth/mcp_auth.py), [mcp_token.py](../app/auth/mcp_token.py) | `secrets` in [ecs-task-definition.json](../ecs-task-definition.json) | **Live.** The MCP token secret exists (metadata only, last changed 4 Oct) |
| Amazon CloudWatch | One JSON log line per event, with metrics in Embedded Metric Format | [observability/log.py](../app/observability/log.py), [observability guide](observability.md) | `awslogs` in [ecs-task-definition.json](../ecs-task-definition.json); alarms in [observability template](../infra/observability/template.yaml) | **Live (deployed 18 Oct).** Logs in `/ecs/afterward-mcp`, `/aws/lambda/AfterWardDocumentProcessor` and `/aws/lambda/AfterwardReminderChecker`, each kept 30 days. Three alarms (tool errors, failed-letter queue, MCP health) from the `afterward-observability` stack, actions enabled, all OK, email subscription confirmed. No dashboard. See [observability](observability.md#deployment-status-deployed-18-october-2026-eu-west-2) |
| AWS KMS | Encryption keys | Not called by the application | [kms-key-policy.json](../infra/security/kms-key-policy.json), [s3-encryption.json](../infra/security/s3-encryption.json) (proposals) | **AWS-managed encryption only.** No customer-managed key alias exists. S3 uses SSE-S3, SQS uses SQS-managed encryption, DynamoDB uses its default key, the secret uses the AWS-managed key |
| AWS IAM | Least-privilege roles for the Lambdas, scheduler and ECS tasks | n/a | [infra/security](../infra/security/README.md), [deployment](../deployment/) policy files | Roles referenced by the live resources. Live least privilege is not re-audited here |

## How a letter becomes a plan

1. **S3.** The web app's [upload route](../web/app/api/upload/route.ts) checks the
   file (PDF, under the size limit) and puts it in the documents bucket.
2. **SQS.** The bucket's `s3:ObjectCreated` notification sends a message to the
   `AfterWardDocumentProcessing` queue. After 3 failed attempts a message moves to
   the dead-letter queue, so a bad letter cannot loop forever.
3. **Lambda.** An event source mapping hands each message to
   `AfterWardDocumentProcessor`, which downloads the letter from S3
   ([document_service.py](../app/ingestion/document_service.py)).
4. **Bedrock.** Text is read from the PDF, or by the Bedrock image model for a
   photo. [discharge-letter-check](https://github.com/charvimaurya/discharge-letter-check)
   rejects anything that is not a discharge letter, Claude extracts the plan with
   the package's JSON schema, and the package flags anything a person must confirm
   ([pipeline.py](../app/ingestion/pipeline.py)).
5. **DynamoDB.** The plan is saved to `PostDischargeRecoveryState` with status
   `indexing`.
6. **Titan and S3 Vectors.** Each page is embedded with Titan Text Embeddings V2
   and stored in the S3 Vectors index, tagged with the patient and document.
7. **Ready.** Only after indexing succeeds is the plan marked `ready`. If indexing
   fails, SQS retries the whole letter.

## How the assistant uses MCP

The web app and the Alexa skill both talk to the Python bridge
([web_bridge.py](../app/web_bridge.py)). The bridge runs the assistant on Bedrock
(Converse API) and gives it tools only through the MCP server, over Streamable HTTP
with a bearer token ([client.py](../app/mcp/client.py)):

- **Reads**: `get_recovery_plan`, `get_today_tasks`, `get_medications`,
  `get_week_summary` and `get_recovery_day_details` read DynamoDB.
- **Letter search**: `search_discharge_instructions` embeds the question with Titan
  and searches S3 Vectors, returning the letter's own sentences and page numbers.
- **Writes**: `report_task_completed`, `report_medication_taken` and `undo_report`
  record events in `PostDischargeEventHistory`.

The local code registers these nine tools and two prompts. The live ECS service
runs the `afterward-mcp:latest` image pushed on 8 October, before `get_week_summary`
and `get_recovery_day_details` were added (task definition revision 6, from
18 October, changed only logging), so the deployed MCP server does not have the
current tool set. The demo and video run the MCP server locally; redeploy the ECS
image before claiming cloud parity.

Reminders run separately: EventBridge Scheduler invokes `AfterwardReminderChecker`
every 5 minutes, which reads the plan and saves a pending check-in to DynamoDB for
the web app or Alexa to speak.

## Not used

- **Amazon Bedrock AgentCore.** The application does not use it. An early
  AgentCore starter template was removed from the repository.
- **Amazon Polly.** The web demo uses the browser's own speech, labelled
  **Simulated Alexa+**. The Alexa skill speaks through Alexa itself.
- **Amazon Cognito, API Gateway.** Not used.

The Alexa skill uses the Alexa Skills Kit, an Amazon developer service rather than
an AWS service. See [Running the Alexa skill locally](alexa-skill.md).

## Optional: public web deployment (implementation guide Step 9)

A hosted copy of the web app is **optional** and is **not deployed**. The demo runs
locally: web app, bridge and MCP server on one machine, using the live AWS data
services above. Prepared files, none of them deployed:

- [Dockerfile.bridge](../Dockerfile.bridge) and the
  [bridge ECS template](../deployment/bridge/README.md)
- [amplify.yml](../amplify.yml) and the [Amplify notes](../deployment/amplify/README.md)
- Bridge key from Secrets Manager (`BRIDGE_KEY_SECRET_ARN` in
  [web/lib/bridge.ts](../web/lib/bridge.ts))

## Related documentation

- [Architecture](architecture.md) and the [architecture diagram](architecture.svg)
- [AWS setup and troubleshooting](aws-setup.md)
- [Deployment](../deployment/README.md)
- [Security controls](../infra/security/README.md) and the [security review](security-audit.md)
- [Logging and metrics](observability.md)
- [Data synchronisation between Alexa and the web app](data-synchronisation.md)
- [Package integration and safety review](discharge-letter-check-review.md)
- [AWS resource rename record](aws-name-migration.md)
- [Judge README](../README.md)
