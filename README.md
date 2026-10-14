# AfterWard

A living recovery plan for Alexa+.

## What it does

AfterWard turns a discharge letter into a daily plan for medicines, tasks, appointments, and warning signs.
People can ask questions by voice or text, see the letter passages behind answers, and record completed items.
AWS stores the plan and progress, while reminder checks bring up the next action.

## Demo video

[Watch the demo video](https://example.com/afterward-demo-video) (placeholder).

## Architecture

![AfterWard architecture](docs/architecture.svg)

The web app calls a Python bridge. The Bedrock agent calls authenticated MCP tools to read the plan, search the letter, and save progress. Uploads go through S3, SQS, and Lambda. DynamoDB stores plans and events. S3 Vectors stores searchable passages. EventBridge schedules reminder checks.

See [architecture details](docs/architecture.md).

## Tracks entered

- **Alexa+ track:** a simulated voice companion backed by a working MCP server. See the Simulated Alexa+ note below.
- **AWS Builder:** see [AWS integrations](docs/aws-integrations.md) for services and code links.
- **Open Source:** [discharge-letter-check](https://github.com/charvimaurya/discharge-letter-check) is the standalone Python validator split out of AfterWard.

## How judges can test

[Open the public demo](https://example.com/afterward-demo) (placeholder).

For a local demo, follow the setup below, then open [http://127.0.0.1:3000/demo](http://127.0.0.1:3000/demo).

1. Upload `test_data/doc_001.pdf`. Wait for the new plan to be ready.
2. Open Today. Use **Mark as done** on a medicine or task. Each button reports that specific occurrence through the agent and MCP tools.
3. Check the Done-first display. Completed items appear above Next up. The item just completed appears beside the next action.
4. Ask about a medicine or food. Letter-backed answers show an evidence quote-card with a page reference. Food answers cite the letter when it contains relevant diet advice.
5. Check the highlighted wording for the discussed item. When the passage refers to an appointment, its wording appears with the evidence too. Use **Back to today** to return.
6. Open **Developer view** to inspect the conversation and MCP tool calls.
7. Upload a replacement letter. It asks the bridge to clear the previous plan's saved event history. If that reset fails, the upload response returns `history_cleared=false` and the web server logs the failure. The current page does not clear its conversation on upload; reload to start a fresh conversation.

**13 October update check:** Today completion buttons, Done-first display, evidence quotes, related appointment wording, food citations, and highlighted letter wording exist in this checkout. The requested **Get help strip** is not present. Developer view currently shows the latest eight messages, so **full Developer-view conversation history** is still pending.

Voice input depends on browser support and microphone permission. Text input is available too.

## Local setup

Requires Python 3.11, Node.js 22.18 or newer, npm, and AWS credentials. The local app uses live AWS resources. It does not start a local AWS emulator. Set up the S3 upload pipeline, DynamoDB tables, Bedrock model access, and S3 Vectors first using [AWS setup](docs/aws-setup.md) and [deployment instructions](deployment/README.md).

Use your normal AWS credential chain. If using a named profile, set `AWS_PROFILE` in every terminal that runs a service. Keep credentials and MCP tokens on the server.

| Part | Address |
| --- | --- |
| MCP server | `http://127.0.0.1:8001/mcp` |
| Python bridge | `http://127.0.0.1:8002` |
| Web app | `http://127.0.0.1:3000/demo` |

The MCP port is selected by the startup command. Use 8001 for this local setup. The old README command used 8000. The bridge script defaults to 8002.

### macOS

Install dependencies from a fresh clone:

```bash
git clone https://github.com/charvimaurya/AfterWard-A-Living-Recovery-Plan-for-Alexa.git
cd AfterWard-A-Living-Recovery-Plan-for-Alexa
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install uvicorn pytest tzdata
cp .env.example .env
cd web
npm ci
cp .env.example .env.local
cd ..
```

Fill in `.env` and `web/.env.local` as described below. Add `MCP_URL=http://127.0.0.1:8001/mcp` to the root `.env`.

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
python -m pip install -r requirements.txt
python -m pip install uvicorn pytest tzdata
Copy-Item .env.example .env
cd web
npm ci
Copy-Item .env.example .env.local
cd ..
```

Fill in `.env` and `web/.env.local` as described below. Add `MCP_URL=http://127.0.0.1:8001/mcp` to the root `.env`.

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

### Settings

Root `.env.example`, copied to `.env`:

| Setting | Meaning |
| --- | --- |
| `AWS_REGION` | AWS region for the Python services, normally `eu-west-2`. |
| `MODEL_MODE` | `test` uses `TEST_MODEL_ID`; `final` uses separate extraction and agent model IDs. |
| `TEST_MODEL_ID` | Bedrock model or inference profile used for extraction and chat in test mode; must be filled in. |
| `FINAL_EXTRACTION_MODEL_ID` | Bedrock extraction model used in final mode. |
| `BEDROCK_EXTRACTION_MODEL_ID` | Legacy setting read by config but not used by the current extraction model selector. |
| `AGENT_MODEL_ID` | Legacy setting read by config but not used by the current agent model selector. |
| `IMAGE_MODEL_ID` | Bedrock model for image transcription; needed for image scripts, not the PDF demo upload. |
| `RECOVERY_STATE_TABLE` | DynamoDB table containing the current recovery plan. |
| `EVENT_HISTORY_TABLE` | DynamoDB table containing completion events and other recorded history. |
| `DOCUMENT_BUCKET` | Existing S3 bucket receiving discharge letters. |
| `PROCESSING_QUEUE_URL` | SQS document-processing queue URL used by queue helpers and checks. |
| `S3_VECTOR_BUCKET` | Existing S3 vector bucket storing letter embeddings. |
| `S3_VECTOR_INDEX` | Vector index name within that bucket. |
| `EMBEDDING_MODEL_ID` | Bedrock embedding model used for indexing and search. |
| `EMBEDDING_DIMENSIONS` | Embedding size, which must match the vector index dimensions. |
| `MCP_AUTH_TOKEN` | Local MCP bearer token used by the bridge and checked by the server. |
| `MCP_AUTH_TOKEN_SECRET_ARN` | Secrets Manager token secret for deployment; leave blank for local token authentication. |
| `MCP_ALLOWED_ORIGINS` | Comma-separated origins accepted by the MCP transport. |
| `CLOCK_MODE` | `real` uses current patient-local time; `demo` fixes time; `production` disables test hooks. |
| `DEMO_FIXED_NOW` | ISO timestamp used only in demo clock mode. |

Additional root settings needed by the current code:

- `MCP_URL`: set to `http://127.0.0.1:8001/mcp` so the bridge reaches the local MCP server.
- `FINAL_AGENT_MODEL_ID`: set a Bedrock agent model if using `MODEL_MODE=final`; this setting is missing from the example.

Web `web/.env.example`, copied to `web/.env.local`:

| Setting | Meaning |
| --- | --- |
| `AWS_REGION` | AWS region for the web server's S3 and DynamoDB clients. |
| `DOCUMENT_BUCKET` | Upload bucket; replace `<ACCOUNT_ID>` and match the Python configuration. |
| `RECOVERY_STATE_TABLE` | Recovery table; match the Python configuration. |
| `TEST_PATIENT_ID` | Synthetic demo patient ID; keep `demo_patient_001` for the supplied demo. |

The web server defaults to bridge address `http://127.0.0.1:8002`. Optional `AGENT_API_URL` in `web/.env.local` overrides it.

## Load and reset the demo patient

Upload `test_data/doc_001.pdf` through `/demo` first. This creates the recovery plan for `demo_patient_001`. The reset script does not upload or extract a letter and fails if no plan exists.

For a repeatable recording, set `CLOCK_MODE=demo` in the root `.env`. The supplied `DEMO_FIXED_NOW` is `2026-10-23T07:00:00+01:00`. Restart both Python services after changing settings.

From the repository root, with the virtual environment active on either platform:

```sh
python scripts/reset_demo_patient.py --confirm
```

This clears the demo patient's current-date completions and check-in state. It keeps the letter and plan. It uses the same configured clock as the app. Refresh Today after the reset.

## Run tests

From the repository root, with the virtual environment active:

```sh
pytest -q
cd web
npm test
```

Default pytest discovery excludes live AWS integration tests. The web tests use Node's built-in TypeScript support. See [testing details](docs/testing.md).

## Simulated Alexa+

This demo uses browser speech input and speech output with a Bedrock agent and real MCP tools. It simulates the Alexa+ experience. It is not a deployed Alexa+ add-on. Amazon's [Alexa+ developer documentation](https://developer.amazon.com/docs/alexaplus/add-ons/home.html) says the Category SDK and MCP Toolkit are available only to selected partners.

## Synthetic data only, no real patients

All demo patients and documents are synthetic. Use only the supplied synthetic letters when testing.

## Licence

[MIT licence](LICENSE). Copyright 2026 Charvi Maurya and Shilpa Agarwal.
