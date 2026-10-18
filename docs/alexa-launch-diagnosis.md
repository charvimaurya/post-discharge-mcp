# Alexa launch diagnosis

Local inspection on 18 October 2026, branch `fix/alexa-web-state-sync`.
Existing uncommitted synchronisation changes were preserved.

## Findings

- Bridge `127.0.0.1:8002/bridge/health` returned HTTP 200 with
  `{"status":"ok"}`. MCP listens on 8001 and Next.js on 3000.
- No `cloudflared` or `ngrok` process was present. Neither command was found
  on the inspected shell's PATH. The ngrok status endpoint on port 4040
  refused the connection. The documented public tunnel is therefore unavailable.
- The saved Alexa Developer Console endpoint is inaccessible here. Its URL
  and whether it is stale remain unverified. `skill-package/skill.json` contains
  `https://example.com/alexa`, a placeholder, not evidence of the saved endpoint.
- Read-only access to the configured DynamoDB recovery plan succeeded.
  Authenticated calls to the running local MCP server returned `ok: true` for
  `get_today_tasks` (7 occurrences) and `get_medications` (7 occurrences).
  No turn, reset, completion, or other patient write was executed against AWS.
- `.env` selects `eu-west-2`, `PostDischargeRecoveryState`,
  `PostDischargeEventHistory`, and MCP port 8001. The Web UI selects the same
  region and recovery table and the synthetic `demo_patient_001` identity.
  Alexa resolves that same identity in `app/alexa/handlers.py` through
  `app/mcp/context.py`. Existing processes' inherited environment overrides
  were not inspected, so file settings alone do not prove every process setting.
- `ALEXA_SKILL_ID`, MCP authentication and bridge credentials are configured
  in the root environment file. Values were not printed. Missing signature and
  timestamp flags default to enabled in `app/alexa/skill.py`.
- `POST /alexa` remains registered in `app/web_bridge.py` and exempt from
  bridge-key authentication in `app/auth/bridge_auth.py`. Its Amazon signature,
  timestamp and skill-ID checks remain intact. LaunchHandler was not changed
  by the uncommitted synchronisation patch. No interaction-model change is
  needed to route a LaunchRequest.

The missing tunnel is a verified connectivity blocker. Without the saved Console
endpoint and its request logs, it is not possible to prove that it was the sole
cause of the earlier Console error. No application-code defect was reproduced;
no application or environment-file changes were made for this diagnosis.

## Validation

```sh
./.venv/bin/python -m pytest -q tests/test_alexa.py tests/test_alexa_walk_completion.py tests/test_cross_interface_sync.py
git diff --check
```

Result: **105 passed in 0.90s**; diff check passed. Tests exercise the ASK
dispatcher, valid launch response speech and session fields, signature/skill-ID
refusals, timeout handling, and task persistence/idempotency with isolated storage.
These are automated local tests, not signed requests from Amazon. The separate
live read-only checks above verify backend retrieval, not a complete live launch.
No frontend files changed for this diagnosis, so frontend tests were not rerun.

## Restart and retest on macOS

Ports 8001, 8002 and 3000 were already occupied by the expected services. Do not
start duplicates. If restarting is needed, stop each existing service in its own
terminal first. From the repository root, use separate terminals:

```sh
./.venv/bin/python scripts/run_test_mcp.py --now 2026-10-23T07:00:00+01:00 --port 8001
```

```sh
MCP_URL=http://127.0.0.1:8001/mcp CLOCK_MODE=demo DEMO_FIXED_NOW=2026-10-23T07:00:00+01:00 DEMO_IDLE_RESET_HOURS=0 LOCAL_REMINDER_LOOP=0 ALEXA_FEED_ENABLED=true ./.venv/bin/python scripts/run_web_bridge.py --port 8002
```

```sh
cd web
npm run dev
```

Once `cloudflared` is installed and available in the shell:

```sh
cloudflared tunnel --url http://127.0.0.1:8002
```

Keep the tunnel running. In the Alexa Developer Console, compare **Build →
Endpoint → HTTPS → Default Region** with the newly printed HTTPS tunnel URL
plus `/alexa`, then **Save Endpoints**. Use the wildcard-certificate option
described in [alexa-skill.md](alexa-skill.md). Confirm the Console skill ID
matches your private `ALEXA_SKILL_ID` locally. Do not share its environment file.
Do not use `/mcp`, port 8001, the Web UI URL, or plain HTTP as the skill endpoint.

Changing the shared Console requires the owner's approval. A live launch calls
`run_turn`, which can record chat activity or clear a pending check-in: local
read-only diagnosis does not authorise such a shared-patient test. Use an approved
isolated environment, or obtain approval before testing against shared Margaret.

Once approved, enable Development testing and say `open after ward`. Capture the
simulator response and the bridge's `alexa_request` or `alexa_rejected` log line.
Do not include authorization headers, signatures, tokens or patient text in shared
logs. No bridge request suggests tunnel/endpoint routing; `alexa_rejected` gives
the verification reason; timeout/turn-failure logs indicate downstream failure.
If it still fails, those observations are needed before choosing a code fix.

## Follow-up: tunnel and Python TLS verification

The supplied Cloudflare tunnel was subsequently verified as reachable. Both
local port 8002 and the supplied HTTPS tunnel returned the same results:

| Request | Result |
| --- | --- |
| `GET /health` | 401, `{"error":"Unauthorized."}` |
| `GET /bridge/health` | 200, `{"status":"ok"}` |
| Unsigned synthetic `POST /alexa` | 400, `{"error":"Request refused."}` |

The earlier missing-tunnel finding was a point-in-time observation; it no longer
explains this reachable endpoint. `/health` is not registered and is correctly
caught by bridge authentication. No health-route or authentication exemption
was added.

A separate local failure was reproduced: Python's default CA file and directory
were absent, and `urllib.request.urlopen` to Amazon's Alexa certificate host
failed with `SSLCertVerificationError: CERTIFICATE_VERIFY_FAILED` (unable to get
local issuer certificate). The ASK SDK's `RequestVerifier._load_cert_chain`
uses this urllib path. Its download occurs before signature verification; the
route only catches `VerificationException`, while urllib can raise `URLError`.
Consequently this trust-store failure can abort a signed request before dispatch.
Unsigned tests never download the certificate, explaining why they did not expose
this problem.

Using `ssl.create_default_context(cafile=certifi.where())` restored verified TLS
to the same host. The HTTP 403 for the directory URL is expected evidence that
TLS completed, not a successful Alexa certificate download or signature check.

The minimal fix is in `scripts/run_web_bridge.py`: before starting the local
server, use the certifi bundle only if the default SSL context has no trusted
CA certificates and neither `SSL_CERT_FILE` nor `SSL_CERT_DIR` was explicitly
configured. `certifi` is now a direct pinned dependency. No `.env` edit or
application authentication change is needed. This fallback is for the local
launcher; it does not alter deployed container startup.

After applying the launcher setup in a fresh process, the default SSL context
contained 121 trusted CA certificates and verified TLS to Amazon succeeded.
The running bridge was not restarted automatically.

New regression tests cover empty versus functioning CA stores, preservation of
explicit trust configuration, and real SHA-256 signature validation of synthetic
launch requests without a bridge key. Only the certificate trust anchor and
patient/agent dependencies are injected in those signed tests. Tampering with
the body is rejected before any turn. Amazon chain trust and actual Simulator
delivery remain unverified. Tests also explicitly distinguish `/health` from
`/bridge/health`.

Targeted result: **132 passed in 0.92s**. The successful signed synthetic launch
returned HTTP 200 with Alexa version `1.0` and a `PlainText` speech response.
The tampered request returned HTTP 400 and safe rejection JSON. Captured logs
identify signature rejection without logging credentials or request text.
Full Python suite: **1233 passed, 10 deselected in 3.10s**. `git diff --check`
passed. No frontend files were changed in this follow-up.

The missing Python CA store is a confirmed local defect, with a verified fix.
Attribution of the specific Simulator failure still requires its bridge error
log or a successful Console retest after restart. Do not describe the complete
Amazon request path as verified solely from these tests.

Restart only the bridge using the command above, leaving the working MCP and
tunnel processes running. Retain the same saved tunnel URL with `/alexa` if
the tunnel has not restarted. No interaction-model rebuild is needed. Before
a shared-patient Console launch, obtain the approval described above, since
launch can update chat activity and a pending check-in.

## Follow-up: agent ExceptionGroup after successful Alexa authentication

The reported live request now reaches LaunchRequest and returns HTTP 200, but
logs `agent_turn` and `alexa_turn_failed` with `ExceptionGroup`. This is a
different failure stage from the earlier TLS diagnosis.

A read-only reproduction using `app/mcp/client.py:mcp_turn` and
`call_mcp_tool("get_today_tasks", {})` exposed an `ExceptionGroup` containing
an HTTP `ConnectError`. Its traceback originates in the MCP Streamable HTTP
transport's `_run_request_post` / `_handle_post_request` and HTTP transport
`handle_async_request`. At inspection time port 8002 was listening and port
8001 had no listener. `.env` points MCP_URL at `http://127.0.0.1:8001/mcp`.

`app/mcp/client.py:_open_session` opens and initializes this transport;
`_TurnConnection._hold` forwards opening errors to waiting callers. The agent
uses this session for concurrent fact reads and tools discovery. A missing MCP
server therefore prevents launch's recovery-information retrieval. It is not
evidence of a Bedrock call failure, a signature failure, or a schema regression.
The cryptography deprecation warning does not explain the reproduced connection
failure.

Starting the local MCP server with the command above restored both concurrent,
authenticated read-only tool calls: `get_today_tasks` and `get_medications` each
returned `ok: true` with 7 occurrences. No launch, completion, reset, or metadata
write against shared Margaret was used to verify this recovery. The MCP process
was left running in the execution session (PID 77891 at startup).

The minimal operational fix is keeping MCP running on the configured port.
The bridge does not need restarting for that dependency to become available.
Code changes only improve safe diagnostics: `app/observability/log.py` retains
the wrapper error type and adds bounded `error_causes` containing nested leaf
class names. It never records exception messages, URLs, request text or full
tracebacks. Restart the bridge to load this logging improvement.

Regression tests cover transport-opening failure propagation, nested error-type
logging without sensitive messages, and LaunchRequest's failure response. The
latter is HTTP 200, Alexa version `1.0`, `PlainText` speech explaining that the
assistant could not be reached, a valid reprompt, and a boolean
`shouldEndSession`. It does not claim recovery actions succeeded. No fallback
or request-signature rules were weakened.

Although the backend connection failure is reproduced and resolved locally,
the Simulator's generic response error remains unverified until a real retest.
If it persists with successful MCP calls, inspect the Simulator's actual response
JSON and correlate its request ID with the bridge log before another code change.
