# Product feedback

From building AfterWard between 31 August and 23 October 2026. Every point comes from
real work on this repository; details and dates are in the [friction log](friction-log.md).
Synthetic data only. This is engineering feedback, not patient research.

Each block answers: what we used it for, what worked well, what needs work, how
onboarding went, and whether we would build with it again.

## Amazon Bedrock (Claude Sonnet 4.5 and Haiku 4.5, Titan Text Embeddings V2)

- **Used for:** reading each discharge letter into a fixed form (forced tool output), the demo agent that picks MCP tools, and embeddings for letter search.
- **Worked well:** forced tool output gave dependable JSON. EU inference profiles kept requests in the EU. One `MODEL_MODE` setting switches between Haiku for testing and Sonnet for final runs. CloudWatch shows the tokens each letter uses (about 7,400 in and 2,700 out).
- **Needs work:** (1) the model sometimes answered "your letter doesn't mention driving" without calling the search tool, so we had to add code checks; (2) structured extraction silently drops text that fits no field, which is how the emergency phone number was lost; (3) wording varies between runs, and there is no deterministic mode for demos and tests.
- **Onboarding:** model access and the Converse API were straightforward. The hard part was making sure answers were grounded in the letter.
- **Build with it again?** Yes. Forced tool output made extraction dependable; we would like the "search before answering" check built in.

## Amazon S3 Vectors

- **Used for:** each page of the patient's letter, so answers quote the exact sentence and page, filtered by patient and document.
- **Worked well:** serverless and low cost; the patient filter returned the right passage with its page number.
- **Needs work:** searching an index with no matching vectors returns empty results with no warning. Encryption is fixed when the vector bucket is created. The console cannot show stored passages.
- **Onboarding:** simple setup; the silent empty result was the main blocker.
- **Build with it again?** Yes, for per-patient search at low cost.

## Amazon S3, Amazon SQS and AWS Lambda

- **Used for:** the letter pipeline: upload, queue and worker, with a dead-letter queue.
- **Worked well:** a letter became a ready plan in about 15 seconds, with a clear log line for each stage.
- **Needs work:** buckets, queues and functions cannot be renamed, so renaming the project meant recreating them. Python dependencies need a manual zip or a build script. Missing IAM permissions only showed up during the migration.
- **Onboarding:** the core pipeline was straightforward.
- **Build with it again?** Yes.

## Amazon EventBridge Scheduler

- **Used for:** running the reminder check every 5 minutes, so AfterWard speaks first.
- **Worked well:** it ran with no errors.
- **Needs work:** nothing significant found.
- **Build with it again?** Yes.

## Amazon ECS on Fargate, with Elastic Load Balancing, CloudFront and ECR

- **Used for:** hosting the MCP server over Streamable HTTP.
- **Worked well:** running without a restart since 13 October.
- **Needs work:** new task definitions do not send logs to CloudWatch by default, so errors were invisible. The console shows health "UNKNOWN" when no health check is set. The Host headers sent by the load balancer and CloudFront are not documented for MCP hosting.
- **Onboarding:** we moved here after the AgentCore starter project would not deploy.
- **Build with it again?** Yes, for a long-running MCP endpoint.

## Amazon Bedrock AgentCore

- **Used for:** we tried to host the MCP server on it.
- **Needs work:** three deploys of the starter project in six minutes all stopped with "No resources defined in project".
- **Build with it again?** We would try again once the starter deploys out of the box.

## Amazon CloudWatch

- **Used for:** JSON logs, metrics, and three alarms with email alerts (deployed 18 October).
- **Worked well:** one log line per stage, with no patient details. The alarms deployed from one CloudFormation stack.
- **Needs work:** alarms notify only when they enter ALARM, so one that fired before the email was confirmed never sent a message.
- **Build with it again?** Yes.

## Alexa Skills Kit (custom skill, ask-sdk for Python) and Alexa+

- **Used for:** a custom skill, tested in the Alexa simulator, that uses the same bridge and MCP tools; Alexa+ is simulated in the browser.
- **Worked well:** the SDK's signature and timestamp checks made securing the endpoint easy.
- **Needs work:** the Alexa+ MCP Toolkit is not open to hackathon teams. Alexa waits about 8 seconds, and one reply took 9. Requests do not say which sample phrase matched. Python handlers are sync only. A classic skill cannot speak first. An unsaved tunnel endpoint shows as "skill did not provide a valid response".
- **Onboarding:** the invocation name had to be two words, "after ward".
- **Build with it again?** Yes, and we would be first in line for the MCP Toolkit.

## MCP Python SDK and MCP Apps (tested in MCPJam Inspector)

- **Used for:** the AfterWard MCP server: 9 tools, 2 prompts and an MCP App card.
- **Worked well:** Streamable HTTP on spec 2025-11-25 worked through the load balancer and CloudFront, and the App card rendered in MCPJam Chat.
- **Needs work:** the host allow-list for load balancers and CloudFront is not documented for AWS. The MCPJam Tools pane shows JSON, not the App. How long an App instance lasts across several tools is not documented.
- **Build with it again?** Yes.
