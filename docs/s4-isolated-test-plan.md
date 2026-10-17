# S4 isolation and S5 dependencies

Reviewed 17 October 2026. No shared patient writes are authorized by this plan.

## S4 acceptance and evidence

S2 and S3 are committed. S4 documentation is committed as `19b5e8f`.
The [S4 evidence record](mcp-app-validation.md) reports authenticated discovery of
seven tools and two prompts, the Today HTML resource and tool metadata, and actual
rendering in MCPJam 3.16.1. A web task completion followed by another tool call
rendered a change from 1 of 7 to 2 of 7. The screenshots and four-second clip are
listed in that record. They were not recaptured for this review.

S4 remains partial: later shared-patient reads returned 1 of 7, without an
established cause. A stable controlled update/read-back and the final recording
in the intended host timezone remain outstanding. Live confirmation labels were
not demonstrated because that data had no flagged tasks; fixtures cover them.

## Implemented isolated check

Run from the repository root using the configured development environment:

```bash
python -m pytest -q tests/mcp/test_isolated_repeatability.py
```

The test uses two separate synthetic patient contexts and in-memory replacements
for the RecoveryState and EventHistory table interfaces. It calls the real SDK
registered tools, task expansion, event creation and idempotency logic. It checks
a pending baseline, one completion, five read-backs, unchanged second-patient
state, an idempotent retry, one event and unchanged base plans. A guard fails any
attempt to make a Botocore AWS API call. Pytest restores the patched interfaces;
all simulated state disappears when the test ends.

This is local application-level evidence. It does not test DynamoDB consistency,
pagination, HTTP identity resolution, the web completion workflow or MCPJam.
The existing HTML harness separately checks result rendering. Neither replaces
a real-host repeatability test.

## Optional next isolated host test

A separate test-only launcher could serve the existing MCP application with
in-memory tables, an ephemeral local token and a test-only patient-context
mapping. Bind only to loopback, prohibit AWS calls, expose the same seven tools,
and connect MCPJam through the actual Streamable HTTP transport. Invoke one
completion against memory and compare repeated Today responses and rendered
cards. A later test-only bridge launcher could exercise the web workflow against
the same store. Do not add production authentication bypasses or a patient-ID
argument to tools.

The launcher has now been implemented and run with memory storage. See the
[isolated MCPJam validation result](s4-isolated-validation.md). Merely choosing a different
bearer token cannot isolate the deployed application: current HTTP authentication
maps valid tokens to `demo_patient_001` in `app/mcp/http_auth.py`.

## Shared-patient fallback, approval required

If the exact shared-backend workflow is required, first obtain explicit approval
for one completion and its cleanup, plus a window without parallel reset,
upload or completion activity. No reset is required for this procedure.

1. Record the application clock, patient timezone, plan identity and current
   task occurrence statuses. Read twice and require identical baselines.
2. Choose exactly one pending, unflagged occurrence through the existing web
   workflow. Record its ID privately and the request time. Stop if the plan or
   baseline changes before the write.
3. Mark that occurrence done once. Require a successful write response and read
   the authoritative event and Today result back. Check that only the selected
   occurrence changed and the completed count increased by one.
4. Invoke `get_today_tasks` in MCPJam and compare the new rendered response.
   Repeat backend and host reads immediately, after 5 seconds and after 30
   seconds. Keep this evidence distinct from previously rendered cards.
5. Record 3 to 5 seconds in the intended timezone, with credentials and private
   links hidden. Stop on any unexplained count or plan change.
6. If approved, undo only the test's new completion through `undo_report`.
   Preserve audit history; do not delete events or reset the patient. Verify
   the baseline statuses are restored. If concurrent activity is detected,
   stop and review before cleanup rather than undoing someone else's action.

No shared-patient procedure above has been executed for this review.

## S5 work and dependency order

| Order | Work that can proceed locally | Dependencies and limits |
| --- | --- | --- |
| 1 | Define the seven-day result contract and adherence rules with synthetic fixtures. | Settle morning schedule identification, unknown versus explicitly missed, stopped medicines, undo handling, historical schedule availability and patient-local boundaries. Current taken/undone events do not establish that silence means missed. |
| 2 | Implement pure calculations and tests for DST, missing events, partial doses and historical uncertainty. | Depends on the contract. Current plans cannot prove past schedules if changed; report uncertainty instead of reconstructing an unsupported history. |
| 3 | Add a read-only event reader and authenticated tool with patient-isolation tests. | Depends on calculations. `get_events` currently returns one query page with no strong-consistency option; weekly reads must address completeness and read-after-write guarantees. No live writes are necessary. |
| 4 | Develop `--with-week` seeding against an in-memory store only. | Use explicit synthetic metadata and deterministic keys. Five completed mornings plus one explicitly missed morning must be supported by an agreed event model. Do not manufacture a missed state from missing events. Running the real reset script requires separate approval. |
| 5 | Add weekly UI rendering and protocol fixtures. | Depends on the result contract. Separate Today and weekly state. Decide how the host supplies both results: sharing a resource URI alone does not guarantee both calls reach the same App instance. Do not assume weekly calls retain a Today result. |
| 6 | Register the eighth tool, verify both prompts and run full suites. | Depends on tool and UI tests. This changes current seven-tool assertions and documentation. No deployment is needed. |
| 7 | Validate in a real host using isolated storage, then finalize captions. | Depends on the host launcher and explicit resolution of the original S4 gate. Shared-backend verification remains separate. Claim eight tools or a working weekly strip only after observed verification. |

S5 implementation has not begun. The user has approved isolated MCPJam
validation followed by independent local S5 work, with contract approval required
before writing S5 code. See the [S5 proposal](s5-implementation-proposal.md).
