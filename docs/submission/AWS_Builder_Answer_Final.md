## Which AWS services did we use, and how?

AfterWard runs on more than a dozen AWS services in the London region (eu-west-2). Together they turn a hospital discharge letter into a living recovery plan: one that speaks first, answers from the patient's own letter, and remembers what she has done. Our service-by-service table, with links to the code that calls each one, is in `docs/aws-integrations.md`. It was checked on 18 October 2026, and the MCP server was redeployed on 20 October.

### 1. Amazon Bedrock: understanding the letter
- **Claude** (Converse API, forced tool output) reads each letter into a fixed form: medicines, tasks, appointments, restrictions and warning signs, each with the exact sentence it came from.
- The same Claude model runs the assistant that chooses which tool to call for open questions.
- **Titan Text Embeddings V2** turns letter passages and questions into vectors for search.
- One setting, `MODEL_MODE`, switches between Haiku 4.5 for testing and Sonnet 4.5 for final runs. EU inference profiles keep requests in the EU.
- **The model never has the last word.** Every extracted item passes our open-source rule-based check, `discharge-letter-check`. An unclear dose is held for confirmation, and an unclear field is flagged, never guessed.

### 2. Amazon S3, Amazon SQS and AWS Lambda: the letter pipeline
- **S3** stores the uploaded letter, encrypted at rest. Each upload sends an event to **SQS**.
- A **Lambda** worker reads the letter, calls Bedrock, runs the safety check, saves the plan and indexes the letter.
- After 3 failed attempts, a letter moves to a **dead-letter queue**, so a bad file cannot loop forever.
- Each step is designed to be safe to repeat, so a duplicate message does not create duplicate completions.
- **Result: a PDF becomes a ready plan in about 15 seconds.**

### 3. Amazon S3 Vectors: answers from her own letter
- Each page of the letter is stored with its patient and document ID.
- When she asks "What does my letter say about driving?", search is filtered to her letter only. It returns the exact sentence and page number, which the screen highlights.
- A plan is marked "ready" only after indexing succeeds.

### 4. Amazon DynamoDB: the living plan
- `PostDischargeRecoveryState` holds the plan, today's tasks and medicines, and the reminder waiting to be spoken.
- `PostDischargeEventHistory` records every task done and dose taken, and supports undo while keeping the history.

### 5. Amazon EventBridge Scheduler and AWS Lambda: speaking first
- EventBridge runs a reminder Lambda, `AfterwardReminderChecker`, **every 5 minutes**. It ran with 0 errors over the 3 hours checked on 18 October.
- It finds anything due in the next 30 minutes, skips "only if needed" medicines and unclear items, and saves one pending reminder for the client to speak.
- A classic Alexa skill cannot speak first, so this reminder runs through our simulated Alexa+ client.

### 6. Amazon ECS on Fargate, Amazon ECR, Elastic Load Balancing and Amazon CloudFront: the MCP server
- Our self-hosted **MCP server** (Python MCP SDK, Streamable HTTP, spec 2025-11-25) runs as a container from **ECR** on **ECS Fargate**, behind a load balancer. **CloudFront** is the HTTPS front door.
- It is stateless and scoped to one patient per call: **9 tools** (6 read, 3 write), **2 prompts** and an **MCP App** Today card. It was redeployed on 20 October, and the tools and prompts were checked in MCP Inspector.
- The simulated Alexa+ client and the classic Alexa skill both call the same tools, so the safety rules live in one place.

### 7. AWS Secrets Manager, AWS IAM, Amazon CloudWatch and AWS CloudFormation: running it safely
- **Secrets Manager** holds the MCP bearer token, and the ECS task reads it from there.
- **IAM** gives each Lambda, the scheduler and the ECS task its own least-privilege role.
- **CloudWatch** gets one JSON log line per step, with **no patient data**. The logger drops letter text, medicine names and patient names, and a test enforces this.
- Five metrics are built in. **Three alarms** (tool errors, failed letters, MCP health) are deployed from one **CloudFormation** stack, with email alerts.

## How it fits together
1. **Letter to plan:** S3 → SQS → Lambda → Bedrock (Claude) → discharge-letter-check → DynamoDB and Titan → S3 Vectors → "ready".
2. **Question to answer:** client → Bedrock assistant → MCP server on ECS → S3 Vectors or DynamoDB → answer with the letter's own sentence and page.
3. **Speaking first:** EventBridge → reminder Lambda → DynamoDB → the client speaks it before the task is due.

## What makes our AWS use different
- **AI where understanding is needed, fixed rules where safety matters.** Bedrock reads; plain code checks, and decides anything about medicines, times or emergencies.
- **Serverless where it's bursty, a container where it's always on:** Lambda and SQS for uploads, ECS for the MCP endpoint.
- **Built for failure from day one:** a dead-letter queue, idempotent writes, alarms as code, and no patient data in logs.
- **Every claim is checkable:** the service-by-service table in `docs/aws-integrations.md` links each service to the code that calls it.

**Honest scope:** Alexa+ is simulated in a web app, because the Alexa+ MCP Toolkit is open only to selected partners. We tried Amazon Bedrock AgentCore, but its starter project would not deploy, so we moved to ECS on Fargate. Amazon Polly is not used; the demo uses browser speech. All patient data is synthetic.

Full details: https://github.com/charvimaurya/post-discharge-mcp/blob/main/docs/aws-integrations.md
