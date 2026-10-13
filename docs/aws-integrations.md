AfterWard uses AWS to turn an uploaded discharge letter into a recovery plan and searchable evidence. AWS also supports the agent's answers, stores progress, protects MCP access, and schedules reminder checks.

| AWS service | What it does in AfterWard | File that calls or deploys it |
| --- | --- | --- |
| Amazon S3 | Stores uploaded discharge letters for the document processor to download. | [app/aws/s3_service.py](../app/aws/s3_service.py), [web/app/api/upload/route.ts](../web/app/api/upload/route.ts) |
| Amazon SQS | Queues document-processing work and holds failed messages for retry handling. | [app/aws/sqs_service.py](../app/aws/sqs_service.py), [deployment/redrive-policy.json](../deployment/redrive-policy.json) |
| AWS Lambda | Runs the document processor and the recovery reminder checker. | [lambdas/document_processor/handler.py](../lambdas/document_processor/handler.py), [deployment/README.md](../deployment/README.md) |
| Amazon DynamoDB | Stores the current recovery plan, pending check-ins, and event history. | [app/database/recovery_state.py](../app/database/recovery_state.py), [app/database/event_history.py](../app/database/event_history.py) |
| Amazon Bedrock | Extracts the letter's instructions, creates search embeddings, and runs the conversational agent. | [app/ingestion/bedrock.py](../app/ingestion/bedrock.py), [app/rag/embeddings.py](../app/rag/embeddings.py), [app/agent/service.py](../app/agent/service.py) |
| Amazon S3 Vectors | Stores and searches embeddings of letter passages to find evidence for answers. | [app/rag/vector_store.py](../app/rag/vector_store.py) |
| AWS Secrets Manager | Supplies the bearer token used to authenticate access to the MCP server. | [app/auth/mcp_token.py](../app/auth/mcp_token.py) |
| Amazon EventBridge Scheduler | Invokes the reminder checker every five minutes. | [deployment/README.md](../deployment/README.md), [deployment/reminder-schedule-target.json](../deployment/reminder-schedule-target.json) |
| AWS Identity and Access Management (IAM) | Limits which AWS resources the document processor, MCP server, and reminder checker can access. | [infra/security/iam-document-processor-policy.json](../infra/security/iam-document-processor-policy.json), [infra/security/iam-ecs-task-policy.json](../infra/security/iam-ecs-task-policy.json), [deployment/reminder-policy.json](../deployment/reminder-policy.json) |
| Amazon CloudWatch | Collects application logs and turns embedded metrics into measurements of processing and tool calls. | [app/observability/log.py](../app/observability/log.py), [deployment/README.md](../deployment/README.md) |

## How the parts connect

An upload stores the letter in S3, and SQS passes processing work to Lambda. The processor uses Bedrock to extract the recovery plan, saves it in DynamoDB, and indexes letter passages in S3 Vectors for search. The Bedrock agent calls the MCP server's tools to read the plan, search the letter, and record progress. EventBridge Scheduler runs the reminder Lambda, which checks the plan and saves a pending check-in for the interface to show and speak. See the [architecture](architecture.md) and [architecture image](architecture.svg).
