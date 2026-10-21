# Running AfterWard for judging

> **Scope:** AfterWard is a hackathon prototype using **synthetic patient data only**. The browser is a **Simulated Alexa+** client; the classic Alexa custom skill has been tested in the developer console but is not a published native Alexa+ add-on. Never upload real patient records. The instructions below are based on the repository's published README (reviewed 22 October 2026); recheck against your final commit.

## In 60 seconds: what to evaluate

AfterWard turns a synthetic discharge letter into a persistent recovery plan, then exposes that plan through a voice-oriented web demo, a classic Alexa skill, and a self-hosted MCP server. The critical product distinction is **the plan changes when the patient reports what they did**. The assistant also searches the source letter before answering relevant questions and flags uncertain instructions rather than fabricating missing details.

**Judge resources:** [Main repository](https://github.com/charvimaurya/post-discharge-mcp) · [Open-source validator](https://github.com/charvimaurya/discharge-letter-check) · [AWS integration evidence](aws-integrations.md) · [Product feedback](product-feedback.md) · [Friction log](friction-log.md) · [Architecture](architecture.md) · [Testing](testing.md)

## Prerequisites

- Python **3.11**, Node.js **24**, npm, and Git.
- For the complete pipeline: access to the configured AWS account in **eu-west-2**, Bedrock models, two DynamoDB tables, S3 documents bucket, S3 Vectors index and ingestion Lambda. See [AWS setup](aws-setup.md) and [deployment instructions](../deployment/README.md).
- Copy `.env.example` to `.env` and `web/.env.example` to `web/.env.local`. Follow the comments in these files; generate unique `MCP_AUTH_TOKEN` and `BRIDGE_KEY` values, with identical `BRIDGE_KEY` in both env files. Do not place AWS access keys in env files or commit secrets.
- Use the AWS credential chain or `AWS_PROFILE`. These instructions do **not** provide judge credentials or a public hosted demo.

### Install (Windows PowerShell)

```powershell
git clone https://github.com/charvimaurya/post-discharge-mcp.git
cd post-discharge-mcp
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
Push-Location web
npm ci
Copy-Item .env.example .env.local
Pop-Location
```

For macOS/Linux, see the [README installation steps](../README.md#install). Complete both environment files before starting services.

## Start the three components

Run from the repository root in **three separate terminals** after activating the Python environment where needed.

| Component | Command | Local address |
| --- | --- | --- |
| Self-hosted MCP server | `python -m uvicorn app.mcp.http_server:app --host 127.0.0.1 --port 8001` | `http://127.0.0.1:8001/mcp` |
| Alexa/web bridge | `python scripts/run_web_bridge.py --port 8002` | Port `8002` |
| Next.js client | `cd web` then `npm run dev` | `http://127.0.0.1:3000/demo` |

Windows convenience entrypoint: `.\scripts\start-demo.ps1`, which opens each part in its own window. `-Reset` resets the demo patient first, `-Alexa` starts the tunnel flow, and `-Record` fixes the demo clock to 23 October 2026, 07:00 for that run only (a *simulated* time).

**Do not reset shared state casually.** The web UI's **Reset demo** action and `scripts/reset_demo_patient.py --confirm` clear the synthetic demo patient's daily events; `scripts/ingestion/reingest_demo_letter.py --confirm` replaces their plan. They modify the shared configured data, so use only with permission and a disposable demo account.

## What to demonstrate

These are **test scenarios**, not claims that each currently passes. Use the synthetic Margaret patient and compare displayed results with stored state.

| Scenario | Action in the Simulated Alexa+ UI | Evidence to look for |
| --- | --- | --- |
| Today's plan | Ask what Margaret has due today | Timed tasks and doses from the current plan |
| Task write + memory | Report returning from a walk; ask what remains | Appropriate task marked completed and absent from remaining open items |
| Medication write | Report a **specific** medicine and dose taken | Intended medication occurrence recorded, without duplicates |
| Source-grounded answer | Ask whether Margaret can drive | Search invoked; answer supported by text/page from her synthetic letter, or explicitly says not established |
| Recovery history | Open the weekly dashboard | Seven-day recorded progress, with absent records **unknown**, not assumed missed |
| Unclear instruction | Inspect a flagged ambiguous/missing detail | **Needs confirmation**; no invented instruction |

**Known issue to disclose until retested:** The repository's published final-model evaluation reports **13/14** synthetic scenarios passed, with one ambiguous medication report recorded without clarifying the medicine. Do not present that ambiguity case as a passing safety safeguard unless a later dated evaluation proves the fix. See [testing](testing.md) and [evaluation data](agent-final-evaluation.json).

## MCP compliance and portability

The locally tested MCP endpoint negotiated **`2025-11-25`** using **Streamable HTTP** and responded to `tools/list`. A code check on 22 October 2026 finds **nine tools, two prompts and one MCP App resource** in [app/mcp/server.py](../app/mcp/server.py). This is not a live `tools/list` run; reconfirm against the final commit.

The README documents `get_today_tasks`, `get_medications`, `get_recovery_plan`, `get_week_summary`, `get_recovery_day_details`, `search_discharge_instructions`, `report_task_completed`, `report_medication_taken`, `undo_report`; prompts `ask_my_letter` and `morning_checkin`; and MCP App resource `ui://afterward/today.html`. MCP App rendering requires a compatible client such as MCPJam; the web demo is a separate UI.

### Isolated MCP demonstration (no AWS)

The repository documents an in-memory host. It exposes only a **subset** of tool behavior (today, week and task-completion workflow), not the full Bedrock ingestion or voice experience:

```powershell
python -m tests.mcp.isolated_host --token-file "$env:TEMP\afterward-mcp-token" --with-week
```

Connect an MCP client to `http://127.0.0.1:18001/mcp` using the newly generated bearer token. Use a **new token-file path** on each run; the host does not overwrite an existing file. For the detailed fixture behavior, see [synthetic week history](synthetic-week-history.md).

## Alexa setup — exactly what is and is not shipped

- **Shipped demo surfaces:** local **Simulated Alexa+** browser and a **classic Alexa custom skill** tested through Amazon's developer-console simulator. Neither is a native Alexa+ deployment.
- The classic skill connects to the bridge through a temporary HTTPS tunnel and calls the same underlying MCP tools. For setup, invocation name (`after ward`), and endpoint configuration, see [Alexa skill instructions](alexa-skill.md).
- **Proactive speech** is demonstrated by the browser companion using the EventBridge-fed reminder flow. The classic skill does **not** initiate speech on its own.
- A published README is **not evidence that the tunnel or developer-console configuration is currently live**; confirm each before claiming successful Alexa testing.

## Which features need AWS?

| Feature | AWS-backed demonstration | Isolated local MCP host |
| --- | --- | --- |
| Upload PDF to S3 / trigger SQS–Lambda ingestion | Requires configured AWS resources | No |
| Extract a recovery plan using Bedrock | Requires Bedrock access | No |
| Search source passages using S3 Vectors | Requires configured AWS data | No |
| Live plan, dose and event persistence in DynamoDB | Requires configured AWS tables | No: in-memory fixture only |
| Scheduled reminder events from EventBridge/Lambda | Requires configured AWS resources | No |
| Today card, weekly synthetic data and limited task write | Can run with configured backend | Yes, using isolated fixture |
| Browser voice / classic Alexa skill | Browser/skill + bridge with their documented dependencies | Not provided by isolated host alone |

## How we will measure product success

**North Star — Recovery Days on Track.** Percentage of **evaluable** recovery days where every scheduled activity that requires confirmation is recorded as completed. Report denominator, exclusions and data completeness. This is a **recorded-engagement metric**, **not** medication adherence, treatment effectiveness or a clinical score. Never equate *no recorded event* with *a missed dose*.

| Metric | Definition | Status |
| --- | --- | --- |
| Letter-to-ready-plan time | Elapsed time from upload to plan ready | Instrumented; report measured runs with date and sample size |
| Correct task/dose writes | Successful, idempotent state updates for specified activity | Testable; record final regression counts |
| Source-grounded answer rate | Answers that cite a retrieved passage when the letter supports one | Evaluate on labeled synthetic questions |
| Reminder action rate | Confirmed relevant activity within a declared period after reminder | Future pilot metric; not proven benefit |
| MCP tool-error rate | Failed MCP calls / total calls over declared window | Monitor through configured logs/alarms |
| 30-day readmissions | Clinical outcome against suitable comparison | **Not evaluated**; requires real-world clinical study |

## Verification checklist before linking judges here

- [ ] Final source commit matches the demo recording.
- [ ] README judge links contain real published URLs (no `PENDING_*` placeholders).
- [ ] `tools/list` reconfirms the current number of tools, plus prompts and app resource.
- [ ] Re-run and date the Python/web test, typecheck, build and final-model evaluation results.
- [ ] Verify each *claimed* live AWS service and distinguish local from deployed features.
- [ ] Confirm any ambiguous-medication issue is fixed in tested code **or** prominently disclosed.
- [ ] Check all relative links, `.env.example` coverage and fresh-clone setup.
- [ ] Verify public GitHub access logged out; remove all secrets and real patient data.
