# Fresh-clone verification

Implementation guide Step 8: can a new developer reproduce AfterWard from the
README alone? Run on 18 October 2026.

**Result: PARTIAL.** On macOS, the documented install, every test suite, the
production build and the read-only runtime chain (web app, bridge, MCP server,
live DynamoDB and S3 Vectors) all work from a fresh clone. Not yet shown: an
anonymous clone from GitHub (the repository is private), the Windows PowerShell
commands, and the flows that write to the shared demo patient.

## What was tested

| Item | Value |
| --- | --- |
| Commit | `2257d8ceba2593d532f5e317f32f92a25a9709a7` ("Step 7: README for judges") |
| Clone | `git clone` of the local repository into a new temporary folder outside the project; no `.env`, `.venv` or `node_modules` copied |
| Platform | macOS (Darwin 25.4.0, Apple silicon) |
| Python | 3.11.8 (python.org build), new virtual environment |
| Node.js / npm | 24.21.0 / 11.19.0 |
| AWS | None for tests and runtime check A. Runtime check B used the normal AWS credential chain (`~/.aws`), as the README says; no credentials were written to the clone |
| Secrets | `MCP_AUTH_TOKEN` and `BRIDGE_KEY` were new random values made for the clone, not copied |

## Commands executed

Install, exactly as in the README (macOS):

```bash
git clone <repository> AfterWard-A-Living-Recovery-Plan-for-Alexa
cd AfterWard-A-Living-Recovery-Plan-for-Alexa
python3.11 -m venv .venv            # python.org Python 3.11.8
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
cp .env.example .env
cd web && npm ci && cp .env.example .env.local && cd ..
```

Tests, with no AWS credentials reachable (`AWS_PROFILE` and keys unset,
`AWS_SHARED_CREDENTIALS_FILE` and `AWS_CONFIG_FILE` pointed at missing files,
`AWS_EC2_METADATA_DISABLED=true`):

```bash
python -m pytest -q
cd web && npm test && npm run typecheck && npm run build
```

Runtime, on spare ports so the existing local stack was not touched: MCP server
`18101`, bridge `18102`, web `13100`, using the README's commands with only the
ports and `MCP_URL` / `AGENT_API_URL` changed to match.

## Test counts

| Suite | Result |
| --- | --- |
| `pip install -r requirements-dev.txt` | Succeeded in 12.6 s; `pip check`: no broken requirements; `discharge-letter-check` 0.1.0 from the pinned release |
| `npm ci` | 67 packages in 2.3 s |
| `pytest -q` (whole suite, no AWS) | **1257 passed, 10 deselected** (integration tests that contact real AWS) |
| MCP (`tests/mcp`) | 80 passed, 3 deselected |
| Ingestion (`tests/ingestion`) | 163 passed |
| Agent (`tests/agent`) | 474 passed |
| Crisis replies (`tests/agent/test_crisis.py`) | 53 passed |
| Reminders and proactive check-ins (8 files in `tests/`) | 105 passed |
| Alexa skill (5 files) | 108 passed |
| Auth (`tests/auth`) | 25 passed |
| `npm test` | **138 passed**, 0 failed |
| `npm run typecheck` | Passed |
| `npm run build` | Passed; 16 routes including `/demo` and `/demo/recovery` |
| Agent test plan (`scripts/evaluate_public_demo.py`, final model `eu.anthropic.claude-sonnet-4-5-20250929-v1:0`, synthetic in-memory tools, 12 Bedrock calls) | **13 of 14 passed**. The failing case is the same as the recorded run (see Remaining issues) |

The 10 deselected integration tests are in `tests/aws/test_sqs.py` (1),
`tests/database/test_phase5_actions.py` (6) and `tests/mcp/` (3). They were not
run, because some write to live AWS resources.

## Runtime checks completed

**A. Template settings only (no secrets filled in, no AWS).** Everything starts and
fails closed:

| Check | Result |
| --- | --- |
| MCP `GET /health` | 200 `{"status":"ok","service":"AfterWard MCP"}` |
| MCP `POST /mcp` without a token | 401 |
| Bridge `GET /bridge/health` | 200 `{"status":"ok"}` |
| Bridge `GET /today` with `BRIDGE_KEY` empty | 503 "Bridge authentication is not configured." |
| Web `/demo` and `/demo/recovery` | 200 |

**B. README Settings filled in (new random keys, `CLOCK_MODE=demo`), AWS from the
credential chain, read-only calls only:**

| Check | Result |
| --- | --- |
| Web `GET /api/today` (web → bridge → MCP → DynamoDB) | Margaret, "Friday 23 October, 07:00", 7 tasks, 7 medicines |
| Web `GET /api/week-summary` | 17 to 23 October, 7 days |
| Web `GET /api/recovery-day?date=2026-10-23` | 6 medicines, 1 task |
| Web `GET /api/conversation` | 200 |
| Web API from another origin | 403 |
| Bridge without `X-Bridge-Key` | 401 |
| MCP `tools/list` with the clone's token | 9 tools, matching the README |
| MCP `get_today_tasks`, `get_medications`, `get_recovery_plan` | ok; Margaret's plan |
| MCP `search_discharge_instructions("Can I drive?")` | 5 letter passages with page numbers (Titan + S3 Vectors) |

The clone's bridge log showed no calls to any route that writes (`/chat`, `/reset`,
`/tasks/complete`, `/reminders/check`, `/greeted`, `/documents/*`).

## Checks blocked or not run

| Check | Why |
| --- | --- |
| `git clone` from the README's GitHub URL by a stranger | The repository is private: an anonymous `git ls-remote` asks for a login. Resolved by implementation guide Step 10 |
| Windows PowerShell commands | Only macOS was available |
| Chat (`/api/chat`), task completion, uploads, Reset demo, reminder checks | They change the shared demo patient; not run without permission |
| Opening `/demo` in a browser, voice | The page itself posts the greeting and reminder checks, which write to the shared patient |
| Alexa skill from the clone | Needs a tunnel and the Alexa developer console |
| `pytest -m integration` | Contacts and writes to live AWS |

## Fixes made during verification

- `README.md`: says to run the web app with `npm run dev` locally, because the
  production server (`npm start`) refuses API requests without an HTTPS
  `APP_ORIGIN`; adds `npm run build` to the test commands; links this page.

## Remaining issues

1. **Repository access (blocks a stranger at step one).** Make the repository
   public or invite the judges (guide Step 10), then repeat the clone anonymously.
2. **Windows not verified.** Run the README's PowerShell blocks once on Windows.
3. **Agent case golden-6 fails, as recorded.** "I took my medicine." records a
   dose without asking which medicine (`report_medication_taken`, no model call).
   Same result on 17 and 18 October. Listed in the README's limitations.
4. **`web/next-env.d.ts` is tracked but rewritten by Next.js.** `npm run dev` and
   `npm run build` write different import paths, so the clone shows a modified file
   after building. Harmless; Next.js projects usually git-ignore this file.
5. **Missing `S3_VECTOR_BUCKET` reaches the caller as a generic error.** The MCP
   server logs "S3_VECTOR_BUCKET is not set", but the tool caller only sees
   `UNSTRUCTURED_TOOL_RESULT`. The README lists the setting as required.
6. **Deployed services are older than the code.** The ECS MCP task definition
   predates two tools, and the document Lambda was last updated on 14 October. The
   local demo uses current code; see [AWS integrations](aws-integrations.md).
