# Recovery dashboard

Open `/demo/recovery`, or use **View weekly dashboard** on the This week row
beneath the Today plan on `/demo`. The link sits beside the disclosure, not
inside it, so opening the strip and following the link stay separate actions.
The dashboard opens in a new tab so the chat stays as it was. Its "Back to
Today" closes that tab, or opens `/demo?view=today` (straight to the plan, not
the upload screen) when the browser keeps the tab open. The dashboard uses the Today screen's frame, top bar, panels and cards. The Today
page's five-second polling is unchanged.

The calendar starts on the first day with saved history (or recorded tasks), never
later than today, and fills the rest of its seven tiles with the days ahead, which
cannot be opened. The totals count only the shown days up to today. To give the
demo patient history on past days, run `scripts/seed_demo_history.py` (preview by
default; `--confirm` writes, `--remove` deletes exactly what it wrote). It writes
to the live Event History table; Reset demo keeps those days, a new upload removes
them. See `app/demo_history.py`.

After pulling this change, restart both the MCP server and the web bridge. A
process started before `get_recovery_day_details` existed answers
`Unknown tool`, and the page then shows "Recovery history could not be checked".

## What is shown

- Seven patient-local calendar days ending today, with accessible date buttons,
  an outline for today and a selected-date state.
- Weekly cards: confirmed mornings, saved recovery-task completion count, and
  days with insufficient medication history. These are not a clinical score.
- Selected-date scheduled medicines: saved name, dose, period, status and
  completion/recorded timestamp. Confirmation warnings are preserved. Missing
  names or doses are explicitly unavailable, never filled from guesses.
- Task activity with saved completion timestamps. Medication events do not count
  as recovery tasks.
- Conditional synthetic provenance, loading/error states, manual Refresh and
  patient-timezone timestamp formatting. Long tables scroll on small screens.

The dashboard refreshes weekly and selected-date data every five seconds. It
rejects stale responses after date changes, cancels requests on unmount and
hides old daily details if a refresh fails. It never submits completion actions.
Polling reads the full, paginated patient history: two history reads per cycle
can increase DynamoDB read costs. This suits a small demo, not an unbounded
production history without a date index or materialised summaries. Existing
read quotas and server-side credentials remain in force.

## Contract and safety

The new read-only MCP tool is `get_recovery_day_details(date: str)`. Date must be
in the last seven patient-local days. It has no patient argument and resolves
identity through the existing authenticated MCP context. The registered count
is now **9 tools and 2 prompts**. Existing running/deployed MCP processes retain
the old count until restarted or separately approved for deployment.

The bridge exposes protected `GET /recovery-day?date=YYYY-MM-DD`, and Next.js
exposes `/api/recovery-day` with existing origin checks, read limits and no-store
responses. Additional query parameters, patient IDs and duplicate dates are
rejected. The response omits patient identity and credentials.

The day result has `kind: recovery_day_details`, `schema_version: 1`, `date`,
`timezone`, `as_of`, `scope`, `schedule_evidence`, `synthetic_demo_history`,
`medications` and `tasks`. Rows carry occurrence ID, saved name, status and
`recorded_at`; medicines also include saved dose, period, due time where known
and `needs_confirmation`. Display timestamps use the recorded completion time
when present, otherwise a valid event audit timestamp. Missing/naive timestamps
cannot establish a positive completion.

Historical medication details require complete, versioned schedule snapshots.
A full `medication_schedule_snapshot` is preferred; an existing
`morning_schedule_snapshot` supports morning-only detail and is labelled as
such. Missing/conflicting full snapshots never fall back to today's plan.
Historical task snapshots are optional; task action records can still be shown
without inventing a historical task denominator.

Weekly adherence remains scheduled morning doses only, excluding PRN and
explicitly inactive medicines. Missing records are unknown, not missed.
Explicit missed events, unknown, not-yet-due and evidenced empty schedules stay
distinct. Undo and deterministic event keys prevent double counts. Today can
use the current schedule; it is never expanded backward into historical dates.
Existing ordinary action events without a historical plan version do not prove
adherence to a historical schedule.

No DynamoDB migration is required. Normal production writes do not automatically
start producing historical schedule snapshots as part of this change. Thus
historical details can remain unknown until trustworthy snapshots exist.

## Safe synthetic preview, no AWS

From the repository root:

```sh
./.venv/bin/python scripts/run_recovery_dashboard_demo.py --port 8003
```

In a separate terminal, start Next.js with the isolated bridge URL. If a Next
server already runs from this checkout, stop it first; do not run two dev servers
against the same `.next` directory.

```sh
cd web
AGENT_API_URL=http://127.0.0.1:8003 npm run dev
```

Open `http://127.0.0.1:3000/demo/recovery`. Root `.env` and `web/.env.local`
BRIDGE_KEY values must already match, as for the regular bridge. The preview
uses existing bridge authentication and exposes only dashboard reads. AWS SDK
calls are explicitly forbidden in memory mode. It does not serve Alexa, chat,
reset, upload or task-completion endpoints; switch back to the normal bridge URL
when returning to the interactive `/demo` workflow. It is mocked-storage
verification, not proof of DynamoDB or Alexa integration.

The isolated identity is `isolated_week_demo`, the timezone is Europe/London,
and the fixed clock is 23 October 2026 at 07:00 BST. Fixture medicines and doses
are explicitly synthetic, not clinical advice. Expected evidence:

| Date | Morning medicines | Tasks recorded complete |
| --- | --- | --- |
| 17–19 October | Unknown, no schedule evidence | 0 |
| 20 October | Both taken | 1 |
| 21 October | One taken, one explicitly missed | 1 |
| 22 October | One taken, one unknown | 1 |
| 23 October | Both taken | 1 |

Weekly summary: **2 of 7 mornings confirmed**, **4 task completions**. This is
computed from 23 synthetic events, not hardcoded in the dashboard.

## Optional DynamoDB seed, never automatic

Preview makes no AWS calls:

```sh
./.venv/bin/python scripts/seed_recovery_dashboard.py
```

Only after explicitly approving the target tables, conditionally seed the
reserved synthetic identity:

```sh
./.venv/bin/python scripts/seed_recovery_dashboard.py --confirm --region eu-west-2 --state-table <approved-state-table> --event-table <approved-event-table>
```

This requires GetItem/PutItem on the state table and Query/GetItem/PutItem on the
event table. No tables or IAM resources are created. Each write is conditional;
retries verify identical content. Existing different plans or history cause a
refusal, including a real record occupying the reserved identity. It never
resets, deletes, overwrites or writes to `demo_patient_001`. Interrupted runs
can be rerun; there is no automatic rollback deleting records.

The existing demo token still resolves to Margaret. Seeding does **not** switch
that mapping or silently change `/demo` to another patient. To read the seeded
identity in the isolated, read-only preview:

```sh
./.venv/bin/python scripts/run_recovery_dashboard_demo.py --read-aws --region eu-west-2 --state-table <approved-state-table> --event-table <approved-event-table> --port 8003
```

This separate mode uses GetItem/Query, reads only `isolated_week_demo`, requires
a synthetic plan marker and does not expose writes. No AWS seed or read mode was
executed during implementation.

## Files and validation

| File | Change |
| --- | --- |
| `app/mcp/tools/recovery_day.py` | Day evidence validation, deduplicated actions, undo and read-only context-based reader |
| `app/mcp/tools/week.py` | Require aware action timestamps for confirmations; exclude PRN snapshots |
| `app/mcp/server.py` | Register the ninth read-only tool |
| `app/web_bridge.py` | Authenticated day-details read route |
| `app/recovery_dashboard_seed.py` | Pure deterministic synthetic plan and history |
| `scripts/seed_recovery_dashboard.py` | Preview-first, conditional, idempotent optional seed |
| `scripts/run_recovery_dashboard_demo.py` | Isolated authenticated read-only preview, memory or explicit DynamoDB reads |
| `web/app/api/recovery-day/route.ts` | Validated server-only bridge proxy |
| `web/app/demo/week-panel.tsx` | Dashboard navigation from the existing summary |
| `web/app/demo/afterward.css` | Summary-link styling |
| `web/app/demo/recovery/page.tsx` | Date selection and cancellable polling |
| `web/app/demo/recovery/dashboard.tsx` | Calendar, summaries and daily tables |
| `web/app/demo/recovery/recovery.css` | Responsive AfterWard styling |
| `web/lib/recovery-dashboard.ts` | Defensive parser, timestamp formatter and snapshot fetcher |
| `tests/test_recovery_dashboard.py` | Historical, seed safety, identity, auth and real-tool/memory integration tests |
| `tests/mcp/test_prompts.py`, `test_today_app.py`, `test_week_summary.py`, `test_isolated_host.py` | Expect ninth tool while preserving prompts/resource checks |
| `web/tests/recovery-dashboard.test.ts` | Data parser, refresh/date flow and actual React-rendered output |
| `web/tests/sync-api-routes.test.ts` | Actual Next route validation/forwarding regression |
| `web/tests/week-summary.test.ts` | Existing weekly panel includes navigation |
| `docs/recovery-dashboard.md` | This report and safe operating instructions |

Validation commands:

```sh
./.venv/bin/python -m pytest -q
cd web
npm test
npm run typecheck
npm run build
```

Automated coverage includes partial/missing schedules, repeated/conflicting
records, missing timestamps, undo/retake, stopped/PRN medicines, local midnight,
provenance, foreign patient filtering, wrong browser parameters, authentication,
seed reruns and refusal of unrelated records. Integration uses real Python MCP
tool functions and readers with memory storage; Next route tests inject only
server dependencies. React tests render actual components but are not browser
interaction tests or Amazon NLU verification.

Local results: **1257 Python tests passed, 10 deselected**; **137 Web tests
passed, 0 failed**; `npm run typecheck`, `npm run build` and `git diff --check`
passed. The build includes `/demo/recovery` and `/api/recovery-day`. The
standalone seed script's default preview was also run without AWS calls.

Still pending: responsive visual inspection in a browser; approved live Alexa
completion followed by DynamoDB event read-back, dashboard polling and browser
reload; live undo/idempotency checks; actual historical-snapshot production;
and any DynamoDB-backed isolated seed/read validation. Nothing was deployed or
committed as part of this implementation.
