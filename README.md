# AfterWard

AfterWard is a post-discharge companion prototype with document ingestion, structured recovery plans and a browser voice interface labelled **Simulated Alexa+**.

Deployment configuration uses AfterWard resource names. The [migration record](docs/aws-name-migration.md) describes retained rollback resources; their full current availability has not been reverified.

Use `DOCUMENT_BUCKET` for the S3 bucket setting. `AFTERWARD_BUCKET` is also
accepted by the Python configuration as a compatibility fallback; the web server uses
`DOCUMENT_BUCKET`. Bucket values must refer to an existing bucket.
See [deployment instructions](deployment/README.md) for building
`build/afterward_document_processor.zip` and the updated configuration paths.

- `app/mcp/`: authenticated MCP server and recovery-plan tools
- `app/`: ingestion, RAG, AWS services, and database operations
- `lambdas/`: Lambda entry points
- `deployment/`: deployment configuration and dependency pins
- `build/`: generated packages (excluded from Git)
- `tests/`: project tests

## Judge links and scope

| Item | Link or status |
| --- | --- |
| Public demo | **PENDING_DEMO_URL**. A hosted frontend has not been verified. |
| Three-minute video | **PENDING_VIDEO_URL** |
| Devpost | **PENDING_DEVPOST_URL** |
| Application repository access | **PENDING_REPOSITORY_ACCESS**. Anonymous GitHub API lookup returned 404 for the configured origin; judge access is not established. |
| Reusable package | [discharge-letter-check](https://github.com/charvimaurya/discharge-letter-check) |
| Package CI | [Verified three-version run](https://github.com/charvimaurya/discharge-letter-check/actions/runs/38950242737), Python 3.11/3.12/3.13 |
| Engineering feedback | [Product feedback draft](docs/product-feedback.md), not submitted externally |

Use synthetic data only. This prototype has not been clinically validated.
The medication safety issues below block patient-facing use.

## Prototype and hosting status (17 October 2026)

The current application registers **eight MCP tools**: get_recovery_plan,
get_today_tasks, get_medications, search_discharge_instructions,
report_task_completed, report_medication_taken, undo_report and get_week_summary.
An earlier authenticated read-only check found **six tools** at one deployed
CloudFront endpoint, without undo_report or get_week_summary. The other endpoint
timed out. That listing was not refreshed in this review. Current read-only AWS
metadata confirms the hosting resources, not source parity or a working demo.

The verified MCP hosting path is CloudFront → ALB → ECS Fargate (MCP). The former
`AfterWardMCP/` AgentCore template has been removed from the repository; the
application does not use AgentCore. Voice uses browser speech synthesis/recognition; this is a **Simulated
Alexa+** experience, not a verified native Alexa+ integration or Amazon Polly.

`discharge-letter-check` v0.1.0 supplies the extraction schema, instruction types
and validation helpers. AfterWard owns ingestion orchestration, recovery state,
retrieval, agent behavior and reminders. Its four v0.1.0 integration checks pass.
The separate package main is v0.2.0, but a source compatibility probe failed three
of four checks; no upgrade was applied. See the [package review and medication
safety findings](docs/discharge-letter-check-review.md).

A hosted frontend and end-to-end public demo have **not** been verified. Bridge
and Amplify configurations are prepared, not deployed; shared-patient safety and
Next.js/Amplify compatibility remain release blockers. See the
[submission readiness review](docs/submission/readiness-review.md),
[demo test report](docs/public-demo-final-test-report.md),
[video script](docs/submission/video-script.md) and
[submission checklist](docs/submission/checklist.md).

## Architecture

The browser talks to Next.js server API routes, which call the authenticated
Python bridge/agent. The agent uses MCP tools to read the plan, retrieve letter
passages and record reported completion. Service credentials stay server-side;
bridge authentication does not provide visitor or patient isolation.

Uploads follow S3 → SQS → document Lambda → Bedrock extraction → DynamoDB, with
letter passages indexed in S3 Vectors. Configured reminder checks run through
Scheduler/Lambda. The observed MCP hosting path is CloudFront → ALB → ECS/Fargate.
These components and their verification scope are listed in
[AWS integrations](docs/aws-integrations.md). Bridge and Amplify deployment files
are preparations, not a verified hosted frontend. Browser speech is labelled
**Simulated Alexa+**; native Alexa+, Polly and AgentCore hosting are unverified.

## Run it locally

To run AfterWard on Alexa from your own Windows machine, follow
[Running the Alexa skill locally](docs/alexa-skill.md): setup, the five
terminals, connecting the skill, a quick check and troubleshooting.

## Setup and local checks

Use Python 3.11 for AfterWard and Node.js 24 for `web/`. The reusable package's
three-version CI does not establish Python 3.12/3.13 support for the whole app.
A full local web workflow still needs the configured AWS services and authorized
synthetic data. Do not run uploads, resets or task writes against shared Margaret.

From a fresh clone:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install pytest
# Copy only when .env does not already exist.
test -f .env || cp .env.example .env
```

Fill `.env` using your authorized development configuration: region, model IDs,
DynamoDB tables, bucket, queue, vector bucket/index, private `MCP_AUTH_TOKEN` and
`BRIDGE_KEY`. Set `MCP_URL=http://127.0.0.1:8001/mcp` for the local workflow.
Use your normal AWS credential chain or `AWS_PROFILE`; never commit credentials.
Replace the example local token and use distinct deployment secrets. In test model
mode, `TEST_MODEL_ID` must name an accessible model; final mode requires
`FINAL_EXTRACTION_MODEL_ID` and `FINAL_AGENT_MODEL_ID` (add the latter explicitly
if it is absent from your environment template). See [.env.example](.env.example).

Run the default checks without enabling live integration tests:

```bash
python -m pytest -q
cd web
npm ci
npm test
npm run typecheck
npm run build
```

The current checkout passed **878 Python tests, 10 live integrations deselected**,
**73 web tests**, typecheck and a production web build in this review. See the [review results](docs/discharge-letter-check-review.md).
These are checkout results, not proof of a clean machine or deployed workflow.

For an AWS-free, isolated MCP App preview, from the root with the venv active:

```bash
python -m tests.mcp.isolated_host --token-file /private/tmp/afterward-local-token --with-week
```

Connect MCPJam to `http://127.0.0.1:18001/mcp` using the private ephemeral test
token. Storage is mocked memory and AWS calls are blocked. Only Today, task
completion and weekly summary are enabled in that test host. Do not use production
tokens. The [S4](docs/s4-isolated-validation.md) and
[S5](docs/s5-implementation-report.md) reports explain the observed host checks.

For the normal AWS-backed MCP server, use a separate terminal:

```bash
source .venv/bin/activate
python -m uvicorn app.mcp.http_server:app --host 127.0.0.1 --port 8001
```

For the normal bridge, use another terminal with the same configured local MCP URL:

```bash
source .venv/bin/activate
export MCP_URL=http://127.0.0.1:8001/mcp
export LOCAL_REMINDER_LOOP=0
python scripts/run_web_bridge.py
```

For the web UI, copy `web/.env.example` to `web/.env.local` only if absent. Set the
same private `BRIDGE_KEY`, `AGENT_API_URL=http://127.0.0.1:8002` and authorized AWS
settings. From `web/`, run `npm run dev`, then open `http://localhost:3000/demo`.
Use localhost consistently for browser requests; the S4 check observed a 403 from
the alternate 127.0.0.1 browser origin. See [web setup](web/README.md).

The normal HTTP authentication maps valid tokens to the shared demo identity.
Starting services does not isolate it. The legacy
[HTTP smoke script](scripts/test_mcp_http.py) can write task completion and is not
a judge health check; it was not executed in this review.

### macOS

Install dependencies from a fresh clone:

```bash
git clone https://github.com/charvimaurya/AfterWard-A-Living-Recovery-Plan-for-Alexa.git
cd AfterWard-A-Living-Recovery-Plan-for-Alexa
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
cp .env.example .env
cd web
npm ci
cp .env.example .env.local
cd ..
```

Fill in `.env` and `web/.env.local` as described in Settings below.

Terminal 1, from the repository root:

```bash
source .venv/bin/activate
python -m uvicorn app.mcp.http_server:app --host 127.0.0.1 --port 8001
```

Terminal 2, from the repository root:

```bash
source .venv/bin/activate
python scripts/run_web_bridge.py --port 8002
```

Terminal 3, from the repository root:

```bash
cd web
npm run dev -- --port 3000
```

### Windows PowerShell

Install dependencies from a fresh clone:

```powershell
git clone https://github.com/charvimaurya/AfterWard-A-Living-Recovery-Plan-for-Alexa.git
cd AfterWard-A-Living-Recovery-Plan-for-Alexa
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
cd web
npm ci
Copy-Item .env.example .env.local
cd ..
```

Fill in `.env` and `web/.env.local` as described in Settings below.

Terminal 1, from the repository root:

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.mcp.http_server:app --host 127.0.0.1 --port 8001
```

Terminal 2, from the repository root:

```powershell
.\.venv\Scripts\Activate.ps1
python scripts/run_web_bridge.py --port 8002
```

Terminal 3, from the repository root:

```powershell
cd web
npm run dev -- --port 3000
```

If PowerShell blocks activation, run `.\.venv\Scripts\python.exe` in place of `python` for Python commands. Activation is not needed with that path.

### MCP Prompts and MCP App

The server exposes two prompts alongside its eight tools. Retrieving a prompt
returns instructions for the client; it does not execute tools.

- `ask_my_letter(question)` requires the patient's question and instructs the
  agent to call `search_discharge_instructions` first, using that question.
  Answers must use relevant returned letter passages, cite page numbers when
  available, and acknowledge anything that could not be verified. It prohibits
  invented medical instructions or medication changes.
- `morning_checkin()` takes no arguments. It references `get_today_tasks` and
  `get_medications`, then requests one short, spoken-friendly summary of what
  is complete and what comes next. It requires confirmed data and performs no
  medication-taking actions.

Margaret's Today card renders actual task results with a completed/total count,
progress bar, completed ticks and available completion times, a highlighted next
actionable pending task, and **Needs confirmation** labels where flagged.
Its count covers tasks, not medications. It handles empty or unavailable results
and initially displays **Waiting for today's plan**.

The `get_today_tasks` tool links to `ui://afterward/today.html` through
`_meta.ui.resourceUri`. The resource serves
[`app/mcp/ui/today.html`](app/mcp/ui/today.html) with MIME type
`text/html;profile=mcp-app`. The standalone page receives tool results through
the MCP Apps host protocol. Run the tool again to fetch changed backend state;
a previously rendered response is not a live subscription.

The normal local MCP server uses port 8001:

```bash
source .venv/bin/activate
python -m uvicorn app.mcp.http_server:app --host 127.0.0.1 --port 8001
```

The server loads the repository-root `.env`. Configure `MCP_AUTH_TOKEN` locally
without committing it; deployed token configuration can use Secrets Manager.
Start the local MCPJam version used for S4:

```bash
npx --yes @mcpjam/inspector@3.16.1
```

Open its private local access link and add an HTTP/Streamable HTTP connection:

- URL: `http://127.0.0.1:8001/mcp`
- Header format: `Authorization: Bearer <MCP_AUTH_TOKEN>`
- In MCPJam, select **Bearer Token** authentication and enter only the configured
  token value in the masked field. The header above is a placeholder.

Confirm eight tools and the two prompts are discovered. In MCPJam 3.16.1, the
Tools response pane shows JSON and directs you to Chat. Open **Chat/Playground**,
select `get_today_tasks`, and click **Run** to display the Today card. Select the
intended host timezone before recording completion times. Keep authentication
settings and private access links out of screenshots and recordings.

A host must support MCP Apps to render the HTML. Ordinary MCP clients may expose
only the tool result and resource. Local MCPJam 3.16.1 discovery and actual card
rendering were observed in S4, including a captured change from one to two
completed tasks. Later backend reads returned one again, with the cause
unidentified. Stable repeatability on the shared synthetic patient and a final
recording in the intended timezone remain pending. Confirmation labels were
verified with automated fixtures, not flagged live data. Other hosts and the
currently deployed server have not been validated for these new features.

### This week recovery summary

`get_week_summary()` adds an eighth read-only tool and links to the same Today
resource. Its response includes a current Today task snapshot plus seven
patient-local dates, so a fresh MCP App can render both sections independently.
Call this tool in MCPJam Chat/Playground to display **This week**; calling only
`get_today_tasks` still displays the Today card alone in a fresh App.

The strip shows calculated completed days, completed ticks, explicit missed
markers, neutral unknown/not-yet-due states and an outline for today. Missing
medication events never imply missed doses. Historical schedules require explicit
dated evidence; today's plan is not projected backwards. Existing history
without that evidence is shown as unknown.

Real MCPJam 3.16.1 rendering was verified with isolated in-memory synthetic data,
including independent Today and weekly App instances. This is not DynamoDB or
deployment verification. The **Synthetic demo history** label is restricted to
recognized test identities with synthetic evidence. For memory-only testing:

```bash
python -m tests.mcp.isolated_host --token-file /private/tmp/afterward-week-token --with-week
```

Connect MCPJam to `http://127.0.0.1:18001/mcp` with the private test token. The
launcher blocks AWS calls and supports only Today, task completion and the weekly
tool; other registered tools are disabled in this test environment. Omitting
`--with-week` produces no seeded history. This flag belongs to the isolated test
launcher, not `reset_demo_patient.py`. Never use production credentials here.
See the [S5 implementation report](docs/s5-implementation-report.md) for tests,
evidence and limitations. Local captions can say **8 tools, 2 prompts**; deployed
capability must be verified separately.

### Weekly history in the web demo

Open `/demo`, then **Open today's plan**. The **This week** strip sits beneath
Today's task list and shows seven patient-local days. It loads through
`/api/week-summary` → the authenticated bridge → `get_week_summary`, using the
same server-resolved patient as other MCP calls. Restart the local bridge after
updating it so `/week-summary` is available; the MCP server must expose the eighth
tool. Existing hosted MCP deployments must be checked separately.

The strip refreshes after a recorded action or reset and has a **Refresh** button.
It does not scan event history on every five-second Today poll. Missing historical
schedule/completion evidence is **Unknown**, never automatically missed. Today
uses the current medication occurrence reader, so recording every scheduled
morning dose updates today's indicator, and undoing one removes that confirmation.
The current schedule is never projected onto earlier dates. Historical days still
need saved schedule evidence; this implementation does not create that history.
Only explicit synthetic provenance displays **Synthetic demo history**. No history is
seeded by opening this page. Browser rendering and refresh were verified with
mocked API responses; this is not a live DynamoDB adherence verification.

## Built with, and where to find it

| Technology | Location |
| --- | --- |
| mcp-apps | [app/mcp/ui/today.html](app/mcp/ui/today.html) |
| discharge-letter-check v0.1.0 | [Schema integration](app/ingestion/bedrock.py), [validator boundary](app/ingestion/validator.py) |

## Known limitations before publication

- Medication normalization loses incoming stopped status; the package can leave
  missing doses and uncertain timing unflagged. Unflagged means the checks ran,
  not that clinical correctness or a complete dose was established.
- The saved final-model evaluation is **13/14**, with an ambiguous medication-write
  failure. It was not rerun in this documentation review.
- Visitors share a demo patient, and conversation/crisis state is process-local.
  The earlier shared-state regression remains unexplained. Isolated memory tests
  do not verify DynamoDB consistency or public multi-user isolation.
- Weekly adherence needs explicit historical schedule/action evidence. Without
  it, days remain unknown. Mocked seeding does not populate shared Margaret.
- Upload/abuse controls, TLS, live least privilege and Amplify compatibility need
  deployment-level verification. Customer-managed KMS encryption is not confirmed.

See the [package review](docs/discharge-letter-check-review.md),
[security review](docs/security-audit.md) and
[submission checklist](docs/submission/checklist.md). Missing submission links
remain placeholders; nothing was published by this review.

## Documentation

- [Repository guide: setup, file map, workflow, and testing order](docs/REPOSITORY_GUIDE.md)
- [Architecture](docs/architecture.md)
- [Testing](docs/testing.md)
- [AWS setup and troubleshooting](docs/aws-setup.md)
- [AWS integrations](docs/aws-integrations.md)
- [Deployment](deployment/README.md)

- [Package integration and safety review](docs/discharge-letter-check-review.md)
- [Engineering product feedback](docs/product-feedback.md)
