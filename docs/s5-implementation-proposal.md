# S5 approved contract and implementation plan

Approved by the user on 17 October 2026. Scope is local development, mocked
seeding and isolated MCPJam validation. No live reset, DynamoDB writes,
deployment or infrastructure changes are included.

## Proposed tool and result contract

`get_week_summary()` is read-only, takes no arguments and resolves patient
identity from the existing authenticated context. Register it with the existing
Today resource metadata. Preserve the other seven tools and both prompts.

Use the existing `{ok, data, message}` envelope. Proposed `data` shape:

```json
{
  "kind": "week_summary",
  "schema_version": 1,
  "timezone": "Europe/London",
  "as_of": "2026-10-23T08:00:00+01:00",
  "today": {"date": "2026-10-23", "tasks": []},
  "week": {
    "start_date": "2026-10-17",
    "end_date": "2026-10-23",
    "completed_days": 5,
    "total_days": 7,
    "synthetic_demo_history": true,
    "days": [
      {
        "date": "2026-10-17",
        "is_today": false,
        "status": "completed",
        "reason": "all_scheduled_morning_doses_recorded",
        "scheduled_doses": 2,
        "taken_doses": 2,
        "explicitly_missed_doses": 0,
        "schedule_evidence": "snapshot"
      }
    ]
  }
}
```

This is a shortened synthetic example. Actual responses contain seven days in
ascending local-date order and calculated counts. Unknown schedules use null
counts rather than pretending zero doses were scheduled. The summary wording is
calculated as `5 of 7 days: all morning medicines taken`, with unknown and missed
states visible in the indicators. No patient ID or credentials enter the UI
result.

The weekly response includes a current Today task snapshot because a host may
create a fresh App instance for each tool call. It can therefore render Today
and This week together without another tool result. Existing `get_today_tasks`
returns remain unchanged. Its result still renders Today alone in a fresh App.
Within one instance, separate Today/week state is retained only for matching
local dates; stale weekly state is cleared on a date change. No automatic tool
calls, extra permissions or custom host-message contract are needed.

If the current Today read fails, return a normal tool error rather than
silently presenting an empty plan. Incomplete historical evidence produces a
valid weekly result with explicit unknown states.

## Adherence rules

- Include today and the six preceding patient-local calendar days. Use aware
  instants and timezone conversions, including DST. Use the application's clock.
- Require explicit, complete schedule evidence for each historical day. Never
  project today's medication list backwards. Missing schedule evidence means
  unknown, even when some taken events exist.
- Proposed additional evidence types are `morning_schedule_snapshot` and
  `medication_missed`, using the existing event envelope. A snapshot identifies
  its local date, timezone, plan version, complete morning occurrence list and
  explicit due instants. New production schedule capture and missed-dose
  recording are outside this local scope. Existing histories without such
  evidence therefore remain unknown.
- Prefer an explicit morning designation in the evidenced schedule. Do not
  invent a cutoff for ambiguous clock times or classify unspecified doses as
  morning. Ambiguous or incomplete schedule data means unknown.
- A completed day requires a nonempty, complete evidenced morning schedule and
  a valid taken record for every expected occurrence. Deduplicate occurrences;
  repeated events cannot inflate adherence. Preserve taken/undo semantics.
- A missed day requires an explicit missed record for an evidenced scheduled
  occurrence. Missing events, an overdue clock time, or partial completion alone
  never establishes a missed dose. Conflicting taken/missed evidence without
  established resolution means unknown.
- Use `not_yet_due` when otherwise-known outstanding doses have explicit future
  due instants. Partial or absent completion after due time remains `unknown`
  with a reason such as `partial_completion` or `no_completion_evidence`.
- Use `no_scheduled_morning_doses` as a neutral state when complete evidence
  explicitly establishes an empty schedule. Do not count it as adherence.
- Handle ended or stopped medicines using date-specific evidence. A current
  stopped status alone cannot establish when historical dosing stopped.
- Show Synthetic demo history only when the dedicated synthetic fixture identity
  and every contributing schedule/action record carry trusted synthetic markers.
  A patient name or arbitrary client-supplied boolean is not sufficient.

## Implementation order and tests

1. Add the contract and a pure calculator in `app/mcp/tools/`, with fixtures for
   missing events/schedules, ambiguous morning designation, repeated events,
   incomplete schedules, partial completion, explicit missed evidence, undo,
   conflicts, empty schedules, stopped medicines and DST/local boundaries.
2. Add a separate complete, paginated, strongly consistent event reader without
   changing existing readers' behavior. Use actual record fields for dates;
   hashed event keys cannot be used as chronological ranges. Test pagination,
   patient filtering and failure handling with fake tables. Read-only queries
   must never write event history or recovery plans.
3. Add the context-resolved tool and metadata. Include a Today snapshot from the
   same patient context and update discovery expectations to eight tools.
4. Add deterministic, in-memory synthetic seeds for six previous days: five
   completed mornings, one explicitly missed morning, and an evidenced current
   day that is unknown or not yet due. Test reruns and synthetic provenance.
   Do not add or execute a live `--with-week` reset path in this phase.
5. Extend the standalone HTML with separate Today/week renderers. Test weekly
   result first, Today result first, independent App instances, date changes,
   malformed results, safe text, accessibility and absence of weekly data.
6. Run Python and web suites; verify eight tools, two prompts and the resource
   link. Enable only the required tools in the isolated host. Validate both
   fresh and sequential App instances in MCPJam with memory storage and record
   that this is not DynamoDB verification.
7. Update local documentation and captions only after observed verification.
   Keep deployed capability claims separate. A later live reset/seed extension
   requires a separate proposal and approval.

The user approved the explicit schedule/missed evidence types, self-contained
weekly response and mocked-only seeding. Shared-state testing and deployment
remain excluded. See [implementation results](s5-implementation-report.md).
