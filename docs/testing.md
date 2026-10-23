# Testing

Run from the project root with the virtual environment active.

```bash
pytest -v
pytest tests/ingestion/ -v
pytest tests/database/ -v
pytest tests/rag/ -v
pytest tests/aws/ -v
```

Default pytest discovery is restricted to tests/ and excludes integration tests.
To deliberately run live AWS checks:

```bash
pytest -v -m integration
```

Integration tests may change patient state or consume queue messages. Manual
scripts can also make billable AWS calls and write data. Run only the intended check.

## Manual checks

```bash
# Local PDF extraction and chunking
python -m scripts.ingestion.test_extraction
python -m scripts.rag.test_real_chunking

# Bedrock structured extraction
python -m scripts.ingestion.test_phase3
python -m scripts.ingestion.test_phase3_image

# Embeddings, indexing, retrieval, patient isolation
python -m scripts.rag.test_embedding
python -m scripts.rag.test_real_vector_indexing
python -m scripts.rag.test_rag_search
python -m scripts.rag.test_patient_isolation

# Full asynchronous S3 -> SQS -> Lambda -> database flow
python -m scripts.ingestion.test_full_ingestion
```

## Proactive reminder, locally

On AWS the EventBridge schedule starts the reminder Lambda
(`lambdas/reminder_checker/handler.py`). Locally, the `/demo` page asks for
the same check when the Today screen opens, and again every 60 seconds while
it stays open:

```
/demo page -> POST /api/reminders/check (Next.js) -> POST /reminders/check (bridge)
           -> reminder handler, once -> then GET /api/today
```

Same handler, same rules. The bridge passes `{"demo_now": DEMO_FIXED_NOW}`
(or `{}` when the clock is not pinned) and ignores anything the caller sends,
so the browser cannot choose the patient, date or time. The reply is the
handler's result: `created`, `already_reminded` or `nothing_due`; an error
returns 502. A created reminder is a real write to the RecoveryState table.

## Local reminder loop (optional)

The deployed reminder Lambda is meant to be started by an EventBridge
schedule. Locally, the web bridge can stand in for that schedule:

```bash
LOCAL_REMINDER_LOOP=1 DEMO_FIXED_NOW=2026-10-23T07:00:00+01:00 \
MCP_URL=http://127.0.0.1:8001/mcp python scripts/run_web_bridge.py
```

Every `REMINDER_LOOP_SECONDS` (default 15) the bridge calls the same
handler, `lambdas/reminder_checker/handler.py`, with
`{"demo_now": DEMO_FIXED_NOW}` (or `{}` when the clock is not pinned) and
prints one line: `created`, `already_reminded`, `nothing_due` or `error`.
The reminder rules are not copied; an error is logged and retried on the
next tick. A created reminder is a real write to the RecoveryState table,
exactly as the Lambda would make. The web page picks it up through
`/today` within 5 seconds. Without `LOCAL_REMINDER_LOOP=1` the loop does
not run.

A passing mock-based test does not prove cloud permissions, deployed code, or
medical extraction accuracy. Compare extraction output against the synthetic
source document. The sample PDF is
test_data/letter1_margaret_knee_replacement_SYNTHETIC_Oct20.pdf, two pages.

See ../scripts/README.md for script groups and ../tests/README.md for test groups.
