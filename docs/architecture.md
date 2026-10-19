# Architecture and tech choices

AfterWard turns a hospital discharge letter into a daily recovery plan that a
patient can talk to. It is built on AWS in eu-west-2 (London) and uses synthetic
data only.

![AfterWard architecture](architecture.svg)

## How it works: three paths

### A. A letter becomes a plan

1. The letter (a PDF) is uploaded to a private **Amazon S3** bucket with a
   pre-signed URL.
2. S3 puts a message on an **Amazon SQS** queue. Failed messages go to a
   dead-letter queue with a **CloudWatch** alarm.
3. An **AWS Lambda** worker
   ([`lambdas/document_processor/handler.py`](../lambdas/document_processor/handler.py))
   reads the letter's text with pypdf.
4. **Claude on Amazon Bedrock** fills in a fixed extraction form, using forced tool
   output ([`app/ingestion/bedrock.py`](../app/ingestion/bedrock.py)).
5. **[discharge-letter-check](https://github.com/charvimaurya/discharge-letter-check)**,
   our open-source package, checks every item. Anything missing key details, or
   marked unclear or unreadable, is flagged for a person to confirm.
6. The plan is saved in **Amazon DynamoDB**. Each page of the letter is embedded
   with **Titan Text Embeddings V2** and stored in **Amazon S3 Vectors**, so
   answers can quote the exact sentence and page.

### B. The patient talks to the plan

1. The patient speaks or types in the **Simulated Alexa+** web app (Next.js), or
   in the **Alexa skill**, which is tested in the Alexa developer console simulator.
2. A **crisis check runs first** ([`app/agent/crisis.py`](../app/agent/crisis.py)).
   A message showing a risk of self-harm gets one fixed reply with 999 and
   Samaritans, before any AI model or tool runs.
3. Otherwise the agent (Claude on Bedrock) picks a tool on the **AfterWard MCP
   server**, which reads or records the plan, and gives a short spoken reply.
4. The web app speaks the reply with the browser's own voice (Web Speech API).

### C. AfterWard speaks first

1. **Amazon EventBridge Scheduler** runs a reminder Lambda every 5 minutes.
2. The Lambda finds what is due in the next 30 minutes and saves a pending
   check-in, for example the 07:00 morning medicines.
3. The client speaks it without being asked. The reminder text is built by code,
   not by the model.

## The MCP server

Built with the Python MCP SDK (spec 2025-11-25, Streamable HTTP) and hosted on
**Amazon ECS on Fargate** behind an **Application Load Balancer** and
**Amazon CloudFront**. Every call needs a token and is scoped to one patient.

| Type | Name | What it does |
|---|---|---|
| Read tool | `get_today_tasks` | Today's tasks and doses, and what is done |
| Read tool | `get_medications` | The medicine schedule and its status |
| Read tool | `get_recovery_plan` | The full current plan |
| Read tool | `get_week_summary` | The week at a glance |
| Read tool | `get_recovery_day_details` | One day in detail |
| Read tool | `search_discharge_instructions` | Finds the passage in the patient's own letter |
| Write tool | `report_task_completed` | Ticks off a task, such as walk 1 of 2 |
| Write tool | `report_medication_taken` | Records a dose as taken |
| Write tool | `undo_report` | Undoes the last report |
| Prompt | `ask_my_letter` | Answer a question from the letter, searching for evidence first |
| Prompt | `morning_checkin` | Read today's plan and offer one short next step |
| MCP App | `ui://afterward/today.html` | A visual "today" card, attached to `get_today_tasks` and `get_week_summary` |

Because every rule lives in the MCP tools, not in our demo agent, real Alexa+
could use the same server as its own agent.

## Safety layers

| Layer | What it does | Where |
|---|---|---|
| Crisis check | Fixed safe reply before any AI call | `app/agent/crisis.py` |
| Safety gate | Flags unclear items for a person to confirm | discharge-letter-check |
| Evidence | Answers quote the letter's own sentence and page | `app/rag/`, S3 Vectors |
| Patient scope | Every MCP call and search is limited to one patient | `app/auth/patient_scope.py` |
| Alexa checks | Amazon signature, timestamp and skill ID are verified | `app/alexa/skill.py` |

## Tech choices

Each choice shows why we made it, what we knowingly give up, and the open-source
tool we would use instead.

| Decision | Chosen | Why chosen | Trade-off accepted | Open-source option |
|---|---|---|---|---|
| AWS region | eu-west-2 (London) | Close to UK users; patient data stays in the UK | Some services and models arrive later in London | Any UK or EU server you control |
| Extraction model (final) | Claude Sonnet 4.5 on Bedrock, forced tool output | Reads messy letters well; predictable JSON; nothing to host or train | Cost per document; output can vary between runs, so the safety gate is required | Qwen2.5-VL or Llama 3.3 70B with vLLM |
| Agent model (final) | Claude Sonnet 4.5 on Bedrock, EU inference profile | Good at choosing tools and asking clarifying questions ("which tablet?") | Slower and pricier than Haiku; only needed for our client, since real Alexa+ is its own agent | Qwen2.5 or Llama 3.3 with tool calling, via vLLM or Ollama |
| Dev and test model | Claude Haiku 4.5 | Cheap and fast for many test runs | Lower quality, so golden tests are rerun on Sonnet 4.5 before the demo | A small local model in Ollama |
| Model switching | One `MODEL_MODE` setting (test or final) | Swap every model by changing one setting, no code changes | Two sets of models to keep tested | LiteLLM |
| Reading the letter | pypdf for text PDFs. Photo reading with Amazon Nova is built in the code but not switched on in this build | Text PDFs are read exactly, with no AI guessing at the words | Photos and scans are not supported yet; numbers read from photos would need checking | Tesseract OCR or Qwen2.5-VL |
| Safety gate | discharge-letter-check (our MIT package, v0.1.0) | Rules, not AI, so results are repeatable; 149 tests; reusable by other health apps | Only catches what we have rules for; flags items rather than fixing them | Already open source (MIT) |
| Embeddings | Titan Text Embeddings V2, 512 dimensions | AWS-native, cheap, fits S3 Vectors | Slightly less precise than 1,024; size is fixed once the index exists | BGE or nomic-embed-text |
| Vector store | Amazon S3 Vectors, one index, filtered by patient and document | Serverless and low cost; every search stays inside one patient's letter | Fewer search features than OpenSearch | pgvector, Qdrant or Chroma |
| Database | DynamoDB: RecoveryState and EventHistory | Fast reads by patient; conditional writes make actions safe to repeat; pay per request | No joins; data designed around access patterns | PostgreSQL |
| Document storage | Private S3 bucket | Durable, cheap, encrypted; fires an event on every upload | Key naming must stay consistent | MinIO |
| MCP hosting | ECS Fargate behind ALB and CloudFront, image in ECR | Always-on HTTPS endpoint with no servers to manage | Pays for a running task even when idle | Docker on any VM, with Caddy or Nginx |
| MCP features | 9 tools, 2 prompts, MCP App card | Any MCP client gets the plan, ready-made prompts and a visual card | MCP Apps support differs between clients | Open standard |
| Proactive reminders | EventBridge Scheduler and a reminder Lambda | Managed clock, no always-on server | Real Alexa+ speaking first is not available to us, so the demo client does it | Celery Beat or APScheduler |
| Patient interface | Next.js Simulated Alexa+ app and an Alexa skill | Shows the full flow, including check-ins, without Alexa+ access | Must be clearly labelled as simulated | Already open source |
| Voice out | Browser voice (Web Speech API) | Free and instant, with no server | Sounds a little different on each computer. Next step: Amazon Polly | Piper |
| Monitoring | CloudWatch logs, metrics and a dead-letter-queue alarm | Built in, no extra setup | AWS only | Prometheus and Grafana |

## What is deployed

- **On AWS:** S3, SQS and the dead-letter queue, the document Lambda, DynamoDB,
  S3 Vectors, EventBridge Scheduler and the reminder Lambda, and the MCP server on
  ECS Fargate behind ALB and CloudFront. The cloud MCP task predates the two
  newest tools. See [AWS integrations](aws-integrations.md) for each service, the
  file that uses it and how it was checked.
- **Runs locally:** the web app, the bridge and the demo agent. Bridge and Amplify
  configs are ready for an optional public deployment.
- **Not used:** Amazon Bedrock AgentCore and Amazon Polly. Photo reading (Amazon Nova) is in the code but not switched on.

## Repository map

| Folder | What is in it |
|---|---|
| `app/ingestion/` | Letter reading, extraction and checks |
| `app/rag/` | Page chunking, Titan embeddings, S3 Vectors search |
| `app/mcp/` | MCP server, tools, prompts and the MCP App card |
| `app/agent/` | Demo agent, crisis check and safety rules |
| `app/alexa/` | Alexa skill and its request checks |
| `app/reminders/` | Reminder engine |
| `app/database/` | RecoveryState and EventHistory |
| `lambdas/` | Document worker and reminder Lambda |
| `web/` | Next.js Simulated Alexa+ app |
| `tests/` | 1,264 Python tests; `web/` has 138 more |
