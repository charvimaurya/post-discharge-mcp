# AWS integrations and verification scope

Reviewed 17 October 2026. Implementation/configuration evidence is distinguished
from read-only live metadata. No deployment, patient-data query, secret-value
read or infrastructure change was performed for this review.

| Service | Confirmed use and evidence | Verification scope |
| --- | --- | --- |
| Amazon S3 | Letter download/upload in [s3_service.py](../app/aws/s3_service.py) and the [upload route](../web/app/api/upload/route.ts). | Live bucket default is AES256 (SSE-S3); application uploads also explicitly request AES256. No new upload was performed. |
| Amazon SQS | [Queue adapter](../app/aws/sqs_service.py) and [redrive configuration](../deployment/redrive-policy.json). | Live processing queue reports `SqsManagedSseEnabled=true`. Delivery/retry behavior was not exercised. |
| AWS Lambda | [Document processor](../lambdas/document_processor/handler.py) and [reminder checker](../lambdas/reminder_checker/handler.py). | Handlers and deployment configuration confirmed; neither function was invoked in this review. |
| Amazon DynamoDB | [RecoveryState](../app/database/recovery_state.py) and [event history](../app/database/event_history.py). | DescribeTable confirmed both configured tables. No patient records were read or written. |
| Amazon Bedrock | [Extraction](../app/ingestion/bedrock.py), [embeddings](../app/rag/embeddings.py) and [agent](../app/agent/service.py). | SDK integration confirmed in code. No new model call was made. Earlier evaluation results are separate evidence. |
| Amazon S3 Vectors | [Vector store adapter](../app/rag/vector_store.py). | Store/search integration confirmed in code; live retrieval was not reverified. |
| AWS Secrets Manager | [MCP server token](../app/auth/mcp_auth.py), [client token](../app/auth/mcp_token.py) and prepared bridge/Amplify credential configuration. | DescribeSecret metadata was inspected; secret values were not requested. Bridge/Amplify configuration does not establish deployment. |
| Amazon ECS/Fargate | [MCP task definition](../ecs-task-definition.json). | Live `afterward-mcp-service` in `afterward-cluster` was ACTIVE with one running Fargate task, revision `afterward-mcp:5`, container port 8000. |
| Amazon ECR | The live ECS task definition references `afterward-mcp:latest` on the regional ECR registry. | Image reference confirmed; image content/digest and source parity were not verified. |
| Elastic Load Balancing | CloudFront origins and the MCP service use the application load balancer. | `afterward-mcp-alb` reported active, type application. This is metadata, not an end-to-end health test. |
| Amazon CloudFront | Both inspected distributions point to the MCP ALB. | `E1G5Y3L9QK930` and `E1SEY0O6MW9CTW` reported Deployed and enabled. No frontend journey or fresh endpoint tool listing was tested. |
| Amazon EventBridge Scheduler | [Reminder target](../deployment/reminder-schedule-target.json) and [deployment instructions](../deployment/README.md). | A five-minute schedule is configured in repository files; the live schedule was not reverified. |
| AWS IAM | [Prepared resource policies](../infra/security/README.md) and bridge/Amplify role configurations. | Policies exist. Their existence does not prove live least privilege; prior broad-permission findings remain unresolved. |
| Amazon CloudWatch | [Structured logs and embedded metrics](../app/observability/log.py), [observability configuration](../infra/observability/template.yaml). | Instrumentation confirmed in code. Dashboard, alarms and live log delivery were not revalidated. |

## KMS: what is and is not established

Read-only KMS ListAliases returned AWS-managed aliases, including
`alias/aws/secretsmanager` and `alias/aws/dynamodb`, with no truncated alias page.
Alias existence does not establish that a particular resource uses that key, and
a customer-managed key can exist without an alias.

The inspected S3 bucket explicitly uses AES256, and the queue reports SQS-managed
encryption. The two DynamoDB table descriptions did not return `SSEDescription`;
DescribeSecret did not return `KmsKeyId`. Do not infer a customer-managed key from
those absent fields or claim the application calls KMS directly.

The [customer-managed KMS policy](../infra/security/kms-key-policy.json),
[SSE-KMS proposal](../infra/security/s3-encryption.json) and optional bridge
`SecretKmsKeyArn` permissions are configuration proposals. This review did not
verify a deployed customer-managed KMS integration. No keys were created, rotated,
changed or scheduled for deletion.

## Architecture and limitations

The observed MCP hosting route is **CloudFront → ALB → ECS/Fargate**, with an ECR
image reference. It does not establish a working hosted frontend. Bridge and
Amplify files are deployment preparations. The former `AfterWardMCP/` AgentCore
scaffold is not evidence that the active application uses AgentCore.

The implemented data flow is S3 → SQS → document Lambda → Bedrock extraction →
DynamoDB recovery state, with S3 Vectors for letter retrieval. The agent reads and
records progress through MCP. Configured Scheduler/Lambda reminder checks save a
pending check-in. Those flows were inspected, not executed end to end here.

The browser uses Web Speech APIs, labelled **Simulated Alexa+**. Amazon Polly and
native Alexa+ integration are not established by the current application.

Local code now exposes eight tools and two prompts. An earlier authenticated
endpoint check returned six tools, as recorded in the [dated readiness review](submission/readiness-review.md).
Do not treat local registration, ECS ACTIVE or CloudFront Deployed as proof that
the deployed image contains current code. The [S5 host validation](s5-implementation-report.md)
used in-memory storage, not AWS. See [architecture](architecture.md) and the
[judge README](../README.md).
