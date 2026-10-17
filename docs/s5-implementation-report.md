# S5 local implementation and validation

Reviewed 17 October 2026. Scope: the approved [contract](s5-implementation-proposal.md),
local code, mocked seeding and real MCPJam rendering. No shared Margaret data,
production records or infrastructure were changed. No deployment was performed.

## Implementation

- `app/mcp/tools/week.py`: seven patient-local calendar days, explicit schedule
  evidence and conservative adherence calculation. The context-resolved tool
  returns the existing success/error envelope, a versioned weekly payload and
  a current Today snapshot. Missing schedules or actions remain unknown.
- `app/database/event_history.py:get_complete_patient_events`: a separate,
  paginated, strongly consistent, read-only query. Existing readers are unchanged.
  It reads the patient partition because event keys are hashed, then calculations
  select explicit local dates. Paginated reads are not an atomic snapshot of
  concurrent writes; full-history read cost grows with history size.
- `app/mcp/server.py`: adds the read-only, zero-argument `get_week_summary`, linked
  to `ui://afterward/today.html`. The original seven tools keep their existing
  schemas and implementations; the two prompts remain registered.
- `app/mcp/ui/today.html`: Today plus an optional seven-day strip. Weekly results
  are self-contained. A fresh Today-only result has no strip; same-date updates
  within an App retain separate weekly state, while date changes clear it.
- `tests/mcp/week_seed.py`: deterministic memory-only seed for isolated test
  identities. Five prior completed mornings, one explicit missed morning and
  an evidenced current morning with no invented taken records. Every seeded
  event is synthetic. No live reset-script extension was added.
- `tests/mcp/isolated_host.py`: supports `--with-week` in memory, forces an isolated
  patient, blocks AWS calls and disables unrelated tools. Without the flag, no
  weekly events exist, and the weekly tool returns seven unknown days.

New evidence types are `morning_schedule_snapshot` and `medication_missed` in the
existing event envelope. Snapshots contain an explicit date, timezone, plan
version, completeness flag and occurrence list. Active morning occurrences need
an explicit due instant. Inactive occurrences are excluded only by dated snapshot
evidence. Actions must identify the occurrence and matching plan version.

Existing production history does not automatically gain these records. No
production schedule-capture or missed-dose recording workflow is included. The
correct result for unsupported historical schedules is unknown, not adherence
or missed dosing. The synthetic label is restricted to recognized isolated test
identities with synthetic markers on every contributing evidence record.

## Automated verification

- Full Python suite: **878 passed, 10 deselected in 3.29s** after final code review.
- Web: **73 passed, 0 failed**, duration 295.008291 ms.
- UI harness: **20 checks**, including the original Today cases plus weekly-first,
  independent instances, result ordering, date changes, neutral states,
  provenance, malformed data and JSON-text results.
- New calculation tests cover absent schedules/events, partial completion,
  repeated events, undo/retake, explicit missed evidence, conflicts, incomplete
  schedules, inactive doses, patient filtering, DST and timezone boundaries.
- Reader/tool tests cover pagination, strong-read requests, context isolation,
  generic failures, metadata, eight-tool registration and unchanged records.
- Isolated host tests query with and without seeded history and compare storage
  before and after repeated read-only weekly queries.

## Observed real MCPJam validation

Used MCPJam Inspector 3.16.1 in real headless Chrome, a fresh profile, the actual
Streamable HTTP application at `http://127.0.0.1:18001/mcp` and London host timezone.
Storage was **mocked memory**, with AWS API calls prohibited. This is not DynamoDB
or deployed-service verification.

Protocol checks found exactly **8 tools**, **2 prompts**, the App resource, the
correct MIME type and the UI resource metadata on the weekly tool. Three weekly
calls returned identical results: five completed days, one missed day and today
not yet due. Each included the current three-task Today snapshot.

Actual App frames were observed in this order:

1. `get_week_summary` first: Today showed 0 of 3 done; This week showed
   5 of 7 days, five ticks, a missed dash, a neutral not-yet-due symbol, today
   outlined and Synthetic demo history.
2. `get_today_tasks`: a new independent App rendered Today with the weekly strip
   hidden, while the earlier weekly App retained its historical response.
3. `get_week_summary` again: a third App independently rendered the complete
   Today-plus-week response with the same calculated summary.

Screenshots outside Git:

- `/tmp/afterward-s5-evidence/week-first.png`
- `/tmp/afterward-s5-evidence/week-repeat.png`

The first screenshot was visually inspected. No credentials or private access
links are visible. MCPJam's platform announcement initially covered the eighth
row; dismissing it allowed tool selection. Automation locators also needed to
identify the tool-selection button after previous results added repeated tool
names. Neither issue required application or protocol changes.

## Remaining limits and submission wording

S4's [isolated rendering/repeatability checks](s4-isolated-validation.md) passed;
shared-backend consistency remains partial and the prior regression is
unattributed. S5 has no actual DynamoDB or production validation.

Use **8 MCP tools, 2 prompts** and **This week: synthetic demo history** for local
build slides or clips. Say the weekly summary uses explicit historical evidence
and reports unknown where unavailable. Do not claim the deployed server has eight
tools, that shared Margaret has seeded history, or that missing events mean a
missed medicine. A real reset/seed option and deployment need separate approval.
