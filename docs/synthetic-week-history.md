# Synthetic seven-day history

The **This week** view needs saved history: morning-medicine actions with the
day's schedule, and recovery-task completions. Shared Margaret
(`demo_patient_001`) has saved evidence for only the current demo day, so earlier
days show as unknown. To show a full week without touching shared data, AfterWard
generates a synthetic history **in memory only**.

## Where it comes from

[`tests/mcp/week_seed.py`](../tests/mcp/week_seed.py) builds the events. It:

- refuses any patient except the two isolated test patients
  (`isolated_week_demo`, `isolated_mcpjam_s4`); `demo_patient_001` raises an error;
- imports nothing from AWS and returns a list; it never writes to DynamoDB;
- marks every event `synthetic: true`, so screens label it **Synthetic demo history**;
- is deterministic: the same clock gives the same events and keys.

## The seven-day window

The window is the seven patient-local days ending on the clock's "today" (with
`--with-week`, the isolated host fixes the clock at 23 October 2026, 08:00 London,
so 17 to 23 October). Medicines and tasks use the same seven dates.

| | 6 days ago (Sat) | 5 (Sun) | 4 (Mon) | 3 (Tue) | 2 (Wed) | 1 (Thu) | Today (Fri) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Morning medicines (2 doses) | missed | missed | missed | taken | taken | missed | not yet due |
| Recovery tasks recorded complete | 2 | 3 | 1 (a second was recorded, then undone) | 3 | 2 | 0 | what the session records |

So the week shows **2 of 7 days** with all morning medicines taken: Tuesday and Wednesday.

Each day also gets a morning schedule snapshot, which the weekly summary needs before
it will call a day complete. Today has no seeded task completions: its count comes
from completions actually recorded with `report_task_completed` during the session,
so it always matches the Today card.

Medicines and tasks are separate event types (`medication_*` and
`morning_schedule_snapshot` versus `task_completed` / `task_undone`), and
[`get_week_summary`](../app/mcp/tools/week.py) returns them as two series:
`week.days` (morning medicines) and `week.activity` (task counts).

## How to see it

```bash
python -m tests.mcp.isolated_host --token-file /tmp/afterward-mcp-token --with-week
```

Connect an MCP client (for example MCPJam) to `http://127.0.0.1:18001/mcp` with the
token from that file, record a task with `report_task_completed`, then run
`get_week_summary`. The MCP App shows the task counts and the morning medicines
separately. The host keeps everything in memory and blocks AWS calls; stopping it
discards the history.

## Checks

- [`tests/mcp/test_week_summary.py`](../tests/mcp/test_week_summary.py): seeded
  counts, one shared window across time zones and summer-time changes, medicines
  unchanged by task events, and the patient guard.
- [`tests/mcp/test_week_parity.py`](../tests/mcp/test_week_parity.py): one
  `get_week_summary` result gives the same daily counts and medicine statuses in the
  web app's reader and the MCP App.

## Limitation

This shows how the week view works; it is not real saved history. Shared Margaret's
week fills in only as real events are recorded day by day. The demo clock is fixed
on one day, so in the live demo the six earlier days stay unknown.
