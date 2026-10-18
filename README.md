# AfterWard

**A living recovery plan for Alexa+.** AfterWard reads a hospital discharge letter,
turns it into a daily plan, reminds the patient at the right moment, records what
they did, and answers questions using the letter's own words.

> **Synthetic data only.** Every letter and patient in this repository is invented.
> AfterWard is a hackathon prototype, not a medical device, and has not been
> clinically validated.

## Judge links

| Item | Link |
| --- | --- |
| Demo video | **PENDING_VIDEO_URL** |
| Devpost entry | **PENDING_DEVPOST_URL** |
| This repository | https://github.com/charvimaurya/AfterWard-A-Living-Recovery-Plan-for-Alexa |
| Open-source package | [discharge-letter-check](https://github.com/charvimaurya/discharge-letter-check) (MIT, tests on Python 3.11 to 3.13) |
| AWS integrations | [docs/aws-integrations.md](docs/aws-integrations.md) |
| Hosted demo | None. A public deployment is optional; run AfterWard locally with the steps below. |

## The problem

Leaving hospital comes with a letter full of instructions: tablets at set times,
exercises, walks, wound care, warning signs. At home, with no nurse nearby,
patients and families have to remember all of it alone. A missed instruction or a
misread dose can send someone back to hospital.

## What AfterWard does

1. **Reads the letter.** Upload a PDF or photo. Amazon Bedrock extracts every
   medicine, task, appointment and warning sign, each with the exact sentence it
   came from. The [discharge-letter-check](https://github.com/charvimaurya/discharge-letter-check)
   package flags anything unclear for a person to confirm, so nothing is guessed.
2. **Builds today's plan.** Tasks and doses by time of day, with a weekly view.
3. **Speaks first.** At 07:00 it says what is coming up, without being asked.
4. **Records progress.** "I'm back from my walk" ticks the walk.
5. **Answers from the letter.** "Can I drive?" gets the letter's own sentence and
   page. If the letter does not say, AfterWard says so instead of guessing.
6. **Responds safely to a crisis.** A message showing a risk of self-harm gets one
   fixed reply pointing to 999 and Samaritans, before anything else runs.

## Hackathon tracks

- **Alexa+ track.** A voice-first recovery companion, shown as a **Simulated
  Alexa+** web experience plus an Alexa skill (see below).
- **AWS Builder.** Bedrock, Titan Embeddings, S3, S3 Vectors, SQS, Lambda,
  DynamoDB, EventBridge Scheduler, ECS Fargate, CloudFront and Secrets Manager. See
  [AWS integrations](docs/aws-integrations.md) for each service, the file that uses
  it and its checked deployment status.
- **Open Source.** [discharge-letter-check](https://github.com/charvimaurya/discharge-letter-check)
  is a separate public MIT package, split out of AfterWard. AfterWard installs it
  from the `v0.1.0` release (`requirements.txt`) and uses it for the extraction
  schema and every letter check.

## Architecture

![AfterWard architecture](docs/architecture.svg)

- **Letter to plan:** web upload → S3 → SQS (with a dead-letter queue) → Lambda →
  Bedrock extraction, checked by discharge-letter-check → DynamoDB plan. Each page
  is embedded with Titan and stored in S3 Vectors for search.
- **Conversation:** the web app and the Alexa skill call the Python bridge, which
  runs the Bedrock agent. The agent reads and records everything through the MCP
  server.
- **Reminders:** EventBridge Scheduler runs a Lambda every 5 minutes, which saves
  a check-in for AfterWard to speak.

More detail: [architecture](docs/architecture.md),
[AWS integrations](docs/aws-integrations.md),
[Alexa and web data synchronisation](docs/data-synchronisation.md).

## How AfterWard uses MCP

AfterWard runs its own MCP server ([app/mcp/server.py](app/mcp/server.py)) over
Streamable HTTP with a bearer token. The agent has no other way to read or change
the patient's data.

| Kind | Tools and prompts |
| --- | --- |
| Read the plan | `get_recovery_plan`, `get_today_tasks`, `get_medications`, `get_week_summary`, `get_recovery_day_details` |
| Search the letter | `search_discharge_instructions` (S3 Vectors; returns the letter's sentences and page numbers) |
| Record progress | `report_task_completed`, `report_medication_taken`, `undo_report` |
| Prompts | `ask_my_letter(question)`, `morning_checkin()` |
| MCP App | `get_today_tasks` and `get_week_summary` link to `ui://afterward/today.html`, a Today card that MCP Apps hosts render |

The patient is chosen by the server from the token, never by the model. The
deployed MCP server on ECS was last updated before `get_week_summary` and
`get_recovery_day_details` were added; the demo runs the current server locally.

## The Simulated Alexa+ demo

The Alexa+ developer toolkit is open only to selected partners, so AfterWard shows
the Alexa+ experience in two ways. Neither is a native Alexa+ deployment.

- **Web demo (`/demo`), labelled "Simulated Alexa+".** The browser speaks and
  listens with its own Web Speech API; you can also type. A Developer view shows
  every MCP tool call. **View weekly dashboard** opens a seven-day history.
- **Alexa skill ("open after ward").** A classic Alexa custom skill, tested in the
  Alexa developer console simulator. It talks to the same local bridge through a
  temporary tunnel, so both share one plan. It is not published.
  Setup: [Running the Alexa skill locally](docs/alexa-skill.md).

## Run AfterWard locally

### What you need

- Python 3.11 and Node.js 24 ([web/.nvmrc](web/.nvmrc)).
- An AWS account in eu-west-2 with Bedrock model access, the two DynamoDB tables,
  the documents bucket, the S3 Vectors index, and (for uploads) the deployed
  document Lambda. See [AWS setup](docs/aws-setup.md) and [deployment](deployment/README.md).
- AWS credentials through your normal credential chain or `AWS_PROFILE`. Never put
  access keys in `.env`.

### Install

macOS or Linux:

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

Windows PowerShell:

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

If PowerShell blocks `Activate.ps1`, use `.\.venv\Scripts\python.exe` in place of
`python`.

### Settings

Fill in `.env` (repository root) and `web/.env.local` from their examples. Every
setting is commented in [.env.example](.env.example) and
[web/.env.example](web/.env.example). The ones you must set:

| Setting | File | Value |
| --- | --- | --- |
| `TEST_MODEL_ID`, or `MODEL_MODE=final` with `FINAL_EXTRACTION_MODEL_ID` and `FINAL_AGENT_MODEL_ID` | `.env` | Bedrock model IDs your account can use |
| `DOCUMENT_BUCKET`, `S3_VECTOR_BUCKET` | `.env` | Your AWS resource names |
| `DOCUMENT_BUCKET` | `web/.env.local` | Same bucket |
| `MCP_AUTH_TOKEN` | `.env` | A long random value; replace the example token |
| `BRIDGE_KEY` | both files | The same long random value in both |
| `MCP_URL` | `.env` | Already `http://127.0.0.1:8001/mcp` |
| `AGENT_API_URL` | `web/.env.local` | Already `http://127.0.0.1:8002` |
| `CLOCK_MODE=demo` | `.env` | Optional: fixes the clock at `DEMO_FIXED_NOW` (07:00 on 23 October) so the morning reminder plays. Shown as "Demo time" on screen |

Make a random value with `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
Never commit `.env` or `web/.env.local`; both are ignored by Git.

### Start the three parts

Use three terminals, each from the repository root.

| | macOS or Linux | Windows PowerShell |
| --- | --- | --- |
| 1. MCP server (port 8001) | `source .venv/bin/activate`<br>`python -m uvicorn app.mcp.http_server:app --host 127.0.0.1 --port 8001` | `.\.venv\Scripts\Activate.ps1`<br>`python -m uvicorn app.mcp.http_server:app --host 127.0.0.1 --port 8001` |
| 2. Python bridge (port 8002) | `source .venv/bin/activate`<br>`python scripts/run_web_bridge.py --port 8002` | `.\.venv\Scripts\Activate.ps1`<br>`python scripts/run_web_bridge.py --port 8002` |
| 3. Web app (port 3000) | `cd web`<br>`npm run dev` | `cd web`<br>`npm run dev` |

Open http://127.0.0.1:3000/demo. After changing Python code or `.env`, restart the
MCP server and the bridge. Run the web app locally with `npm run dev`: the
production server (`npm start`) refuses API requests unless `APP_ORIGIN` is set to
an HTTPS address, because it is meant for a hosted deployment.

### Load or reset Margaret, the synthetic demo patient

The demo patient is `demo_patient_001` (Margaret, after a knee replacement).

- **Load her plan** with either:
  - On `/demo`, choose **Upload a discharge letter** and pick
    `test_data/letter1_margaret_knee_replacement_SYNTHETIC_v4.pdf`. This uses the
    deployed S3, SQS and Lambda pipeline.
  - Or process the letter locally with the current code, without S3 or Lambda:
    `python scripts/ingestion/reingest_demo_letter.py --confirm`. This replaces her
    plan.
- **Reset her day** (keeps the plan, clears today's ticks and check-ins): press
  **Reset demo** on `/demo`, or run `python scripts/reset_demo_patient.py --confirm`.

Every visitor shares this one patient. Do not use real patient data.

### Try the MCP server in an MCP client, without AWS

This starts an isolated MCP server with in-memory synthetic data and AWS calls
blocked. It writes a new random token to the file you name (the file must not
already exist):

```bash
python -m tests.mcp.isolated_host --token-file /tmp/afterward-mcp-token --with-week
```

On Windows, use `--token-file $env:TEMP\afterward-mcp-token`. Connect an MCP client
such as MCPJam to `http://127.0.0.1:18001/mcp` with that token as the bearer
token, then run `get_today_tasks` or `get_week_summary` to see the Today card. Only
those tools and task completion are enabled in this mode.

## Run the tests

```bash
python -m pytest -q
cd web
npm test
npm run typecheck
npm run build
```

`pytest` skips tests marked `integration`, which contact real AWS
([pytest.ini](pytest.ini)). The default tests use mocks and need no AWS access.

## Safety and limitations

- **Synthetic data only. Not a medical device. Not clinically validated.** Nothing
  here shows a clinical benefit.
- AfterWard only repeats what the letter says. Unclear items are marked **Needs
  confirmation**, and it will not invent a dose, time or instruction.
- Crisis messages get a fixed reply with 999 and Samaritans (116 123) before any
  model or tool runs ([app/agent/crisis.py](app/agent/crisis.py)). Phrase matching
  cannot catch every way of expressing distress.
- One shared demo patient; conversation memory is held in the bridge process and
  is lost on restart.
- Medication normalisation does not keep a "stopped" status from the letter; see
  the [package review](docs/discharge-letter-check-review.md).
- The recorded final-model evaluation passed 13 of 14 cases, using synthetic
  in-memory tools ([agent-final-evaluation.json](docs/agent-final-evaluation.json)).
  The failure was an ambiguous medicine report that was recorded without asking.
- Voice in the web demo is the browser's own; the Alexa skill runs in the Alexa
  developer console simulator. There is no native Alexa+ deployment and no Amazon
  Polly.

## Documentation

- [Architecture](docs/architecture.md) and [AWS integrations](docs/aws-integrations.md)
- [Running the Alexa skill locally](docs/alexa-skill.md)
- [Recovery dashboard](docs/recovery-dashboard.md)
- [AWS setup](docs/aws-setup.md) and [deployment](deployment/README.md)
- [Logging and metrics](docs/observability.md)
- [Security review](docs/security-audit.md)
- [Testing](docs/testing.md) and the [fresh-clone verification](docs/fresh-clone-verification.md)
- [Friction log](docs/friction-log.md) and [product feedback](docs/product-feedback.md)
- [Repository guide](docs/REPOSITORY_GUIDE.md)

## Licence

[MIT](LICENSE). Copyright (c) 2026 Charvi Maurya and Shilpa Agarwal.
