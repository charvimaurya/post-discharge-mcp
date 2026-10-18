# Alexa, web and dashboard synchronisation

Branch: `fix/alexa-web-state-sync`. No deployment, shared patient reset, AWS write
or skill-console change was performed for this review. Existing uncommitted Alexa
utterance work was carried onto the branch intact.

## Investigation and root causes

These are verified code paths and defects, not a claim that a particular live
AWS request was traced. The deployed bridge, MCP process configuration, Alexa
endpoint and live DynamoDB contents have not been verified.

| Symptom | Evidence before the fix | Resolution |
| --- | --- | --- |
| Alexa completion missing from web | `app/database/event_history.py:get_events` used one query page without `ConsistentRead`; `app/database/recovery_state.py:get_today_tasks` rebuilt status using that reader. A completion outside that page was never seen. `web/app/demo/page.tsx:loadToday` also allowed an older in-flight response to replace a newer post-save read. | Use the complete, strongly consistent event reader and reject superseded Today responses. |
| Web completion missing from Alexa | Both interfaces already use `app.turn.run_turn`, the shared agent and `report_task_completed`. Alexa reloads occurrences every turn in `app/agent/service.py:_load_today`; it has no module-level completion snapshot. Its occurrence reader had the same missing-page/eventual-consistency problem. RecoveryState `get_item` also lacked strong consistency. | Use strong state reads and the same complete event history in both directions. |
| Progress/activity does not change | `web/app/demo/parts.tsx:TodayPanel` already derives the Today ring from `items[].done`. The weekly resource in `app/mcp/tools/week.py` measures morning-medicine adherence, not walks or other tasks. `loadWeek` refreshed only on load/date change or a locally observed save, depending on the optional Alexa feed for external saves. | Invalidate weekly data when polled completion status or reset changes. Preserve medicine semantics and add a separately labelled task-activity series from persisted completion/undo records. |
| Saved progress disappears after returning | `app/demo_reset.py` defaulted to resetting the demo after two idle hours; `/today` and `run_turn` both invoke it. This was an intentional demo feature, not a cache. | Idle reset is opt-in; absent/invalid `DEMO_IDLE_RESET_HOURS` means off. An explicitly configured positive value still resets as before. |
| Selected web task is not reliably recorded | `web/app/demo/page.tsx:tapDone` converted a selected card into a sentence, discarding its occurrence ID and asking the agent to resolve it again. Similar task names or two occurrences in the same part of the day could be ambiguous. | Task buttons now send the exact selected occurrence to the authenticated MCP task tool; medicine buttons retain the existing guarded agent flow. |

The local `.env` and `web/.env.local` were inspected without printing credentials.
Both use `eu-west-2`, `PostDischargeRecoveryState` and the fixed synthetic demo
identity `demo_patient_001`. Python uses `PostDischargeEventHistory`; Next.js does
not read event history directly. The configured MCP URL is
`http://127.0.0.1:8001/mcp`; the development bridge defaults to port 8002. These
file values do not prove what already-running processes inherited from their shells.

## Authoritative data flow

Alexa en-GB intent and `query` slot -> `app/alexa/handlers.py:OpeningHandler` ->
`app/turn.py:run_turn` -> shared agent -> authenticated MCP tool ->
`app/mcp/tools/actions.py:report_task_completed_for_context` ->
`app/database/recovery_state.py:mark_task_completed` -> Event History.

Web typed reports -> `web/app/demo/page.tsx:send` ->
Next.js `/api/chat` -> authenticated bridge `/chat` -> the same `run_turn`,
MCP tool and persistence service. No optimistic completion is saved in the browser.

Web task Mark as done -> `/api/tasks/complete` -> authenticated bridge
`/tasks/complete` -> `report_task_completed` -> the same validated persistence
service. Only `occurrence_id` is accepted; no caller patient/date or medicine-tool
selector is forwarded. The Next.js route keeps origin checks, server-only bridge
credentials and the existing shared chat-action quota. It acknowledges only a
successful MCP result. Medicine buttons continue to use the guarded agent flow.

The base RecoveryState describes the plan. Completed task occurrences are derived
from Event History, not copied back into base task `status` fields. This preserves
repeating occurrences and avoids two competing persisted completion states.

The event writer already records business `completed_at`, UTC audit `recorded_at`
and a deterministic per-patient/occurrence/undo-round key with a conditional put.
Those rules remain intact. Failed persistence cannot produce a successful tool
trace or a completion acknowledgement. A repeated save of one occurrence cannot
create another completion record.

`/api/today` -> bridge `/today` -> MCP task/medicine readers -> complete event
history -> Today list and ring. The ring is not a hardcoded demo total.
`/api/week-summary` -> bridge -> MCP `get_week_summary` -> the same event table ->
`week.activity`: seven `{date, completed_tasks}` entries. Counts are distinct
recorded task occurrences after undo, not percentages, scheduled-dose adherence
or proof that an unrecorded activity was missed. Medicine adherence remains a
separate series requiring actual schedule evidence.

The browser polls Today every five seconds. A completion fingerprint includes the
patient-local date, reset marker, occurrence IDs, status and completion times.
A changed fingerprint invalidates the weekly read, including when Alexa's feed
is disabled, missed or served by another process. Unchanged polls do not reread
all seven days of history. Next.js and bridge responses remain `no-store`.

## Identity, configuration and limits

- The existing demo authentication intentionally maps one bearer token to
  `demo_patient_001`. Alexa and web use that synthetic identity. This is not
  multi-patient account linking.
- MCP write tools accept occurrence IDs, never a patient ID. The shared task
  service validates that the occurrence exists in that patient's current plan.
- Chat, Today and weekly-summary endpoints now reject caller `patient_id`
  selectors with 400, instead of silently processing a different server patient.
  The task-completion route also rejects extra body fields.
  The upload polling endpoint has its own configured-patient check.
- Bridge and MCP processes must use the same `AWS_REGION`, `RECOVERY_STATE_TABLE`,
  `EVENT_HISTORY_TABLE`, `CLOCK_MODE` and `DEMO_FIXED_NOW`. `MCP_URL` must point to
  that MCP process. `web/.env.local` must point `AGENT_API_URL` at that same bridge.
  The Alexa HTTPS endpoint must also reach it. A correct local configuration
  cannot repair a console endpoint still targeting a separate deployment.
- Never put `BRIDGE_KEY` or MCP credentials in `NEXT_PUBLIC_*`. Match the existing
  server-only credentials and restart processes after environment changes.
- No migration, table/index creation or new AWS permission is needed. Existing
  `dynamodb:GetItem` and `dynamodb:Query` permissions are used. Strong reads cost
  more read capacity, and full history pagination grows with the patient's history.
  Multiple query pages are not an atomic transaction during concurrent writes;
  subsequent polling reconciles them. No claim of a global transactional snapshot
  is made.

## Automated validation

Final local results: **1,226 Python tests passed, 10 deselected; 131 frontend
tests passed, 0 failed**. Typecheck, production build, interaction-model JSON
validation and `git diff --check` passed. Gitleaks scanned the changed and new
files without finding leaks. No commit or push was made.

Files changed for synchronisation:

- `app/database/event_history.py`, `app/database/recovery_state.py`: complete,
  strongly consistent reads shared by occurrence status and aggregation.
- `app/demo_reset.py`, `.env.example`: idle reset is an explicit opt-in.
- `app/web_bridge.py`, `web/app/api/chat/route.ts`, `web/app/api/today/route.ts`,
  `web/app/api/week-summary/route.ts`: reject patient selectors.
- `web/app/api/tasks/complete/route.ts`, `app/web_bridge.py`: authenticated exact
  task-occurrence completion using the existing MCP write service.
- `app/mcp/tools/week.py`, `web/lib/week-summary.ts`,
  `web/app/demo/week-panel.tsx`, `web/app/demo/afterward.css`: persisted task
  activity, independent of medicine adherence.
- `web/app/demo/page.tsx`, `web/lib/recovery-sync.ts`: exact task-card mapping,
  stale-read protection and external-completion invalidation.
- `tests/test_cross_interface_sync.py`, `tests/mcp/test_task_activity.py`,
  `web/tests/recovery-sync.test.ts`, `web/tests/sync-api-routes.test.ts`: new
  regression coverage. Existing database, bridge, idle-reset, isolated-host and
  weekly-render tests were updated for the new contracts.
- This report and `docs/alexa-skill.md`: evidence, setup and verification limits.

The preceding uncommitted walk-utterance changes in Alexa handlers, interaction
model, occurrence resolver/service and `tests/test_alexa_walk_completion.py` were
preserved on this branch, not recreated or discarded.

Run from this checkout using its own virtual environment:

```bash
./.venv/bin/python -m pytest -q tests/test_cross_interface_sync.py tests/mcp/test_task_activity.py tests/mcp/test_isolated_repeatability.py
./.venv/bin/python -m pytest -q
cd web
npm test
npm run typecheck
npm run build
```

`tests/test_cross_interface_sync.py` uses synthetic Margaret's identity but replaces
both tables with isolated in-memory implementations. It exercises the real ASK
HTTP handler, bridge HTTP routes, agent, MCP authentication middleware, registered
tool functions and database readers/writer. It deliberately puts the completion
after the first query page, requires strong reads, disables the Alexa feed and
blocks all real AWS SDK calls. MCP transport is an in-process authenticated hop,
not a live JSON-RPC/Streamable HTTP server.

| Check | Automated result |
| --- | --- |
| A. Alexa morning walk -> saved event/timestamp -> web Today -> task activity | Pass against isolated storage |
| B. Web task button -> persisted occurrence -> Alexa sees already recorded | Pass against isolated storage |
| C. New HTTP client/reload retains completion | Pass against isolated storage |
| D. Retry does not add an event or task-activity count | Pass against isolated storage |
| E. Caller patient selectors cannot modify Margaret | Pass; rejected before tool calls |
| F. Failed puts through Alexa, web chat and task button do not confirm or advance progress | Pass against isolated storage |

Frontend tests execute the Next.js route code with a mocked bridge and verify
signed-session forwarding, patient rejection and no-store responses. Component
render tests verify chart values; separate tests verify out-of-order read rejection
and external save/undo/reset invalidation. They are not an observed browser session.

## Local and live verification

The commands above are the safe, reproducible local verification path. They do not
reset, seed or overwrite shared Margaret data. The isolated store is discarded
after each test.

For a live device/browser/DynamoDB verification, first obtain approval and an
isolated environment with Margaret's synthetic plan already provisioned. Do not
point the following processes at shared or production tables. Creating tables,
seeding a plan or changing the shared skill endpoint requires separate approval.

1. Check both terminals' region, table names and patient mapping. Disable idle
   reset and the local reminder loop. Record the baseline occurrence IDs, task
   statuses, relevant event keys and chart counts without credentials.
2. Start the approved isolated MCP process with this checkout's Python:

   ```bash
   ./.venv/bin/python scripts/run_test_mcp.py --now 2026-10-23T08:00:00+01:00 --port 8001
   ```

3. Start its bridge with the same table/region settings already in the environment:

   ```bash
   MCP_URL=http://127.0.0.1:8001/mcp CLOCK_MODE=demo DEMO_FIXED_NOW=2026-10-23T08:00:00+01:00 DEMO_IDLE_RESET_HOURS=0 LOCAL_REMINDER_LOOP=0 ./.venv/bin/python scripts/run_web_bridge.py
   ```

4. Set server-only `AGENT_API_URL=http://127.0.0.1:8002` in `web/.env.local`, start
   `npm run dev` in `web/`, and open `http://127.0.0.1:3000/demo`.
5. Only on an approved isolated Alexa skill, use the existing verified tunnel and
   model setup in [alexa-skill.md](alexa-skill.md). Confirm the endpoint targets the
   same bridge. No shared skill changes were made by this fix.
6. Say "I just came back from my walk". Check its successful write trace, the
   occurrence's persisted event, Today ring/list within about five seconds, and
   the Friday task-activity count after expanding This week. A walk must not
   increase morning-medicine adherence.
7. Mark a different unambiguous task done in the web UI. Ask Alexa about that
   task; it should read it as already recorded. Reload the browser and repeat the
   original walk report; verify one event/count per occurrence.
8. Stop local processes. Preserve the isolated test evidence; do not reset or
   delete shared history as cleanup.

Live Alexa NLU, console endpoint configuration, browser polling against actual
DynamoDB and multi-instance deployment behaviour remain unverified. They must not
be reported as passing on the strength of the automated tests above.
