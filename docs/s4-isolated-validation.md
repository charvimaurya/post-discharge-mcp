# S4 isolated MCPJam validation

Observed 17 October 2026. This exercise used mocked in-memory storage, not
DynamoDB. No shared Margaret data or production records were queried or changed.

## Result

| Check | Actual result |
| --- | --- |
| Server | Existing Streamable HTTP application on loopback port 18001, with test-only storage and identity patches. |
| Isolation | Dedicated `isolated_mcpjam_s4` identity. Storage rejects any other patient. Botocore AWS calls raise an error. Tools outside Today/task completion are disabled in this launcher. |
| Authentication | Missing and incorrect tokens returned 401. A private ephemeral test token permitted initialization. Production tokens were not used. |
| Discovery | Protocol checks found exactly seven tools, both prompts and the Today resource. MCPJam Tools also showed seven tools. |
| Resource | Discovery/read confirmed `ui://afterward/today.html`, HTML content and `text/html;profile=mcp-app`; Today tool metadata linked that resource. |
| Host | Installed MCPJam Inspector 3.16.1, controlled through real headless Chrome using a fresh browser profile. No conversational model call was required. |
| Initial rendering | Chat/Playground Run rendered 0 of 3 done, next walk highlighted and Needs confirmation on a flagged synthetic task. |
| Update | A real MCP `report_task_completed` request wrote one in-memory event through existing application/event logic. This was not the web `/demo` workflow. |
| Read-back | Five protocol reads at approximately 0, 1, 6, 16 and 31 seconds after the write all returned 1 of 3 done. Retrying the completion reported a duplicate. |
| Updated rendering | Two further MCPJam Run calls rendered 1 of 3 done. Observed cards were 0/3, 1/3 and 1/3. Completed tick/time (08:00), next walk and confirmation tag were checked in the actual nested App frame and screenshot. Host timezone was London. |
| Recording | Four-second preview of the real rendered isolated card, assembled from 20 screen captures over 4.001 seconds. Encoded duration 4.000 seconds, size 73,249 bytes. It is not an uninterrupted recording of the update. |

Artifacts outside Git:

- `/tmp/afterward-isolated-evidence/before.png`
- `/tmp/afterward-isolated-evidence/after-repeat.png`
- `/tmp/afterward-isolated-evidence/mcpjam-isolated-4s.mp4`

The updated screenshot was visually inspected. It shows synthetic task text and
no credential fields or private links. Temporary artifacts are not durable
submission assets; copy wanted evidence before clearing temporary storage.

## Test infrastructure

`tests/mcp/isolated_host.py` is an explicit test-only launcher. It uses reversible
process-local patches, local dummy AWS settings, a fixed demo clock, memory
storage and an AWS API guard. It binds only to loopback. It writes a newly
created token file with mode 0600 and removes that file on shutdown. It is not
imported by production startup and does not change production authentication.

```bash
python -m tests.mcp.isolated_host --token-file /private/tmp/afterward-isolated-token
```

Connect MCPJam using `http://127.0.0.1:18001/mcp`, Streamable HTTP and the private
test token. Only Today/task completion operations are enabled, though the normal
seven tool registrations remain discoverable. Do not use a production token or
connect this test profile to the deployed endpoint.

Safety and repeatability tests:

```bash
python -m pytest -q tests/mcp/test_isolated_host.py tests/mcp/test_isolated_repeatability.py
```

Actual full-suite results:

- Python: **858 passed, 10 deselected in 1.66s**.
- Web: **73 passed, 0 failed**, duration 223.897875 ms.
- `git diff --check`: passed.

## Earlier shared-state regression: read-only investigation

The historical 1/7 to 2/7 to 1/7 sequence remains unexplained. The earlier
[friction log](friction-log.md) does not establish an actor or cause.
No new queries of shared state were performed in this exercise.

Code inspection identifies possible mechanisms, not proven causes:

- `app/database/event_history.py:get_events` returns one query page and does not
  request strong consistency. Hashed sort keys do not order events by write time.
- `app/web_bridge.py:document_uploaded` deletes the demo patient's prior event
  history after a new upload.
- `scripts/reset_demo_patient.py:delete_event_history` removes current-day
  completion events when the reset script is explicitly run.
- `app/database/recovery_state.py:undo_completion` records an undo event that
  changes an occurrence back to pending.
- Date-sensitive occurrence IDs depend on the application clock and patient
  timezone, so comparisons must use the same plan, date and clock settings.

The memory test reproduces none of the regression, but cannot rule out actual
DynamoDB read behavior or concurrent shared-patient activity. Audit/request
records would be needed to establish historical attribution.

## Remaining scope

Isolated real-host rendering and application-level repeatability passed. S4
remains **PARTIAL for backend-backed consistency**: no isolated DynamoDB tables
were provisioned or approved, the shared backend was not tested, and the local
web completion workflow was not repeated in isolation. No deployed-service or
production reliability claim follows from this result.

The user's decision permits independent local S5 work after isolated validation,
subject to approval of the proposed S5 contract before implementation. See the
[S5 proposal](s5-implementation-proposal.md).

Temporary test servers and browser were stopped after validation. The temporary
token file was removed. Shutdown testing exposed that Uvicorn re-raises SIGTERM;
the test launcher now routes SIGTERM through its cleanup handler.
