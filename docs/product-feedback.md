# Product feedback

From building AfterWard between 31 August and 23 October 2026. This was our first build on AWS and our first voice agent. Every point below comes from real work on this repository, with dates and details in the [friction log](friction-log.md). Synthetic data only; this is engineering feedback, not patient research.

Each block answers the five Devpost questions: what we used it for, what worked well, what needs work, onboarding, and whether we would build with it again.

## At a glance (AWS Builder)

AfterWard runs in the London region (eu-west-2). Every service below is called by our code and was checked live on 18 October 2026; full table with file links in [aws-integrations.md](aws-integrations.md).

| AWS service | What it does in AfterWard |
|---|---|
| Amazon Bedrock (Claude Sonnet 4.5 and Haiku 4.5) | Reads each discharge letter into a structured plan; runs the assistant that picks MCP tools |
| Amazon Titan Text Embeddings V2 | Turns letter passages and questions into vectors |
| Amazon S3 Vectors | Searches the patient's own letter, filtered to one patient, with page numbers |
| Amazon S3, SQS (with dead-letter queue), AWS Lambda | The letter pipeline: upload, queue, worker |
| Amazon DynamoDB | The recovery plan, reminder state and history of what was done |
| Amazon EventBridge Scheduler | Runs the reminder check every 5 minutes, so AfterWard speaks first |
| Amazon ECS on Fargate, ECR, Elastic Load Balancing, CloudFront | Hosts the self-hosted MCP server over HTTPS |
| AWS Secrets Manager | Holds the MCP bearer token |
| Amazon CloudWatch | JSON logs, five metrics and three alarms with email alerts |

**Our top 3 asks:** open the Alexa+ MCP Toolkit to hackathon teams; make "answer only after retrieval" easy to enforce in Bedrock tool use; report the letter text that a structured extraction did not map to any field.

## Amazon Bedrock (Claude Sonnet 4.5 and Haiku 4.5, Titan Text Embeddings V2)

- **Used for:** reading each letter into a fixed form (forced tool output), the demo agent that chooses MCP tools, and embeddings for letter search.
- **Worked well:** forced tool output gave dependable JSON. EU inference profiles kept requests in the EU. One `MODEL_MODE` setting switches between Haiku for testing and Sonnet for final runs. CloudWatch shows the tokens each letter uses (about 7,400 in and 2,700 out).
- **Needs work:**
  1. The model sometimes said "your letter doesn't mention driving" **without calling the search tool**, although the letter does mention it. We had to add code that sends it back to search first.
  2. Structured extraction **silently drops text that fits no field**. That is how the letter's emergency phone number was lost.
  3. Wording varies between runs, and there is no deterministic mode for demos and tests.
- **Onboarding:** model access and the Converse API were straightforward. The hard part was making answers stay grounded in the letter.
- **Build with it again?** **Yes.** Forced tool output made extraction dependable. We would like a built-in "search before answering" check.

## Amazon S3 Vectors

- **Used for:** storing each page of the letter, so answers quote the exact sentence and page, filtered by patient and document.
- **Worked well:** serverless and low cost. The patient filter returned the right passage with its page number.
- **Needs work:** a query against an index with no matching vectors returns empty results **with no warning**. This cost us about 2 hours when local settings pointed at an old index. Encryption is fixed when the vector bucket is created, and the console cannot show stored passages.
- **Onboarding:** simple setup. The silent empty result was the main blocker.
- **Build with it again?** **Yes**, for per-patient search at low cost.

## Amazon S3, Amazon SQS and AWS Lambda

- **Used for:** the letter pipeline: upload to S3, a message on SQS, and a Lambda worker, with a dead-letter queue after 3 failed attempts.
- **Worked well:** a letter became a ready plan in about 15 seconds, with a clear log line for each stage (received, extracted, checked, saved, indexed, ready).
- **Needs work:** buckets, queues and functions **cannot be renamed**, so renaming the project meant recreating everything and copying letters across (about 3 hours). Missing IAM permissions only showed up mid-migration. Python dependencies for Lambda needed a hand-made zip, so we wrote a build script.
- **Onboarding:** the core pipeline was straightforward once permissions were in place.
- **Build with it again?** **Yes.**

## Amazon DynamoDB

- **Used for:** two tables: the recovery plan and reminder state, and the history of tasks and doses reported.
- **Worked well:** both tables have run with no issues since setup, and every MCP tool reads or writes through them.
- **Needs work:** nothing significant found in our use.
- **Onboarding:** quick to set up.
- **Build with it again?** **Yes.**

## Amazon EventBridge Scheduler

- **Used for:** invoking the reminder Lambda every 5 minutes, so AfterWard speaks first before something is due.
- **Worked well:** it has run on schedule with no errors.
- **Needs work:** nothing significant found.
- **Onboarding:** one schedule and one invoke policy.
- **Build with it again?** **Yes.**

## Amazon ECS on Fargate, with ECR, Elastic Load Balancing, CloudFront and Secrets Manager

- **Used for:** hosting the MCP server over Streamable HTTP, with the bearer token in Secrets Manager.
- **Worked well:** the service has run without a restart since 13 October, and a redeploy on 20 October picked up 9 tools and 2 prompts with no downtime issues.
- **Needs work:** new task definitions **do not send logs to CloudWatch by default**, so errors were invisible until we added logging. The console shows health "UNKNOWN" when no health check is set. The Host header the load balancer and CloudFront send is not documented for MCP hosting (see MCP below).
- **Onboarding:** we moved here after the AgentCore starter would not deploy (see below).
- **Build with it again?** **Yes**, for a long-running MCP endpoint.

## Amazon Bedrock AgentCore

- **Used for:** we tried to host the MCP server on it. It is not used in the final app.
- **Needs work:** three deploys of the starter project in six minutes all stopped with "No resources defined in project".
- **Onboarding:** we could not get past the first deploy.
- **Build with it again?** **Not yet.** We would try again once the starter deploys out of the box.

## Amazon CloudWatch

- **Used for:** one JSON log line per event with no patient details, five metrics in Embedded Metric Format, and three alarms (tool errors, failed letters, MCP health) with email alerts, deployed from one CloudFormation stack on 18 October.
- **Worked well:** one stack created all three alarms, and the logs made each pipeline stage easy to follow.
- **Needs work:** an alarm notifies only when it enters ALARM, so one that fired before the email subscription was confirmed never sent a message.
- **Onboarding:** our IAM user could not use CloudFormation, so an admin had to deploy the stack.
- **Build with it again?** **Yes.**

## Alexa Skills Kit (custom skill, ask-sdk for Python) and Alexa+

- **Used for:** a classic custom skill ("open after ward"), tested in the Alexa simulator, using the same bridge and MCP tools. Alexa+ itself is simulated in the browser and labelled as simulated.
- **Worked well:** the SDK's signature and timestamp checks made securing the endpoint easy.
- **Needs work:**
  1. The **Alexa+ MCP Toolkit is open only to selected partners**, so our working MCP server could not be tried on real Alexa+.
  2. Alexa waits about 8 seconds; one reply took 9 and failed. We moved that answer into code (now about 3 seconds).
  3. A classic skill **cannot speak first**, which is the heart of a recovery companion.
  4. Python handlers are sync only, and requests do not say which sample phrase matched.
  5. An unsaved tunnel endpoint shows as "skill did not provide a valid response".
- **Onboarding:** the invocation name had to be two words, "after ward".
- **Build with it again?** **Yes**, and we would be first in line for the MCP Toolkit.

## MCP Python SDK, MCP Apps, MCP Inspector and MCPJam

- **Used for:** the AfterWard MCP server (spec 2025-11-25): 9 tools, 2 prompts and an MCP App Today card. MCP Inspector and MCPJam for testing.
- **Worked well:** Streamable HTTP worked through the load balancer and CloudFront. The App card rendered in MCPJam Chat with no app changes.
- **Needs work:** the SDK's DNS-rebinding check rejected requests until we added the load balancer and CloudFront host names; this is not documented for AWS hosting. The MCPJam Tools pane shows JSON, not the App. How long an App instance lasts across several tools is not documented.
- **Onboarding:** a basic tool was quick; production hosting behind AWS proxies took about 2 hours.
- **Build with it again?** **Yes.**

## Browser speech recognition (Web Speech API, Chrome)

- **Used for:** speech in for the simulated Alexa+.
- **Needs work:** short words were misheard ("can I" became "can a"). Most seriously, **"I fell in the bathroom" was heard as "I feel in the bathroom"**, so a fall was missed until we added code for likely mishearings. Exposing alternatives and confidence for short phrases would help.
- **Build with it again?** **Only as a stand-in** until real Alexa+ is available.
