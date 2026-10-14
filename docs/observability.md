# Logging, metrics and alarms

AfterWard writes one kind of log line, from one module: `app/observability/log.py`.
Every part of the system uses it: the web bridge, the agent, the MCP server and both Lambdas.

## What a log line looks like

One JSON object per line, on stdout:

```json
{"timestamp":"2026-10-12T00:05:02.849+00:00","level":"info","service":"mcp","event":"tool_call",
 "request_id":"6c3cf2759e634344b45880cf7f3ce002","tool":"get_medications","kind":"read","status":"ok","ms":41}
```

`service` is one of `bridge`, `agent`, `mcp`, `document_lambda`, `reminder_lambda`.

## What may be logged

The module decides, not the caller.

- Only these field names are kept: `event`, `request_id`, `session_id_hash`, `patient_id_hash`, `route`,
  `status`, `ms`, `tool`, `kind`, `reason`, `model`, `tool_calls`, `tokens_in`, `tokens_out`,
  `document_id`, `stage`, `item_count`, `needs_confirmation_count`, `checkin_type`, `error_type`,
  `error_code`, and the five metric names below.
- Any other field is dropped. The line then carries `dropped_fields` with the number dropped.
- Session and patient ids are never logged as they are. `session_id_hash` and `patient_id_hash` are the
  first 12 characters of the SHA-256 of the id, so one patient's or session's lines can be grouped, and
  a known id can be looked up by hashing it, without the id appearing in the logs.
- A kept value must be a number, true/false, or a short code with no spaces (an ID, a route, a
  reason code). A sentence under an allowed name is dropped too.
- Errors are logged by type only (`ValueError`, or `ClientError` with its AWS error code). An
  error's message is never logged, because it can quote the letter.

So a log line never holds message text, replies, letter text, quotes, medicine names, doses or
patient names. `tests/test_no_sensitive_logs.py` runs a full chat turn and a full upload with
those in the data and fails if any reaches a log line.

To log something new, add its name to `ALLOWED_FIELDS` in `app/observability/log.py`. Do not add
a field that could hold free text.

## One request ID, end to end

1. A Next.js `/api` route reuses the caller's `X-Request-ID` if it is ID-shaped, or makes one
   (`web/lib/request-id.ts`), and sends it to the bridge.
2. The bridge keeps it in a contextvar and logs `request_start` and `request_end`.
3. The agent logs `agent_turn` (and `write_blocked` when it refuses to record something).
4. The MCP client sends the ID in the `X-Request-ID` header; each MCP tool logs `tool_call`.
5. `/chat` returns `request_id`. Developer view on `/demo` shows it under the tool calls.

The document Lambda uses the SQS message ID as its request ID, so follow an upload by
`document_id`. A scheduled reminder check uses the Lambda's own request ID.

## Events

| Event | Service | Fields |
|---|---|---|
| `request_start`, `request_end` | bridge | `route`, `status`, `ms` |
| `agent_turn` | agent | `kind` (`code` or `model`), `model`, `tool_calls`, `tokens_in`, `tokens_out`, `status`, `ms`, `session_id_hash` |
| `write_blocked` | agent | `tool`, `reason` (`not_taken`, `which`, `short`, `not_reported`) |
| `tool_call` | mcp | `tool`, `kind` (`read` or `write`), `status` (`ok`, `rejected`, `error`), `error_code`, `ms` |
| `ingest_stage` | document_lambda | `stage` (`received`, `downloaded`, `extracted`, `checked`, `saved`, `indexed`), `document_id`, `ms`, counts |
| `ingest_ready` | document_lambda | `document_id`, `item_count`, `needs_confirmation_count`, `ms`, `upload_to_ready_ms` |
| `ingest_skipped`, `document_failed` | document_lambda | `reason` or `error_type` |
| `extraction_model` | document_lambda | `model`, `reason` (the stop reason), `tokens_in`, `tokens_out` |
| `checkin_created`, `checkin_skipped`, `checkin_failed` | reminder_lambda | `checkin_type` or `reason` |

A tool `status` of `rejected` is an expected answer, such as "nothing to undo". Only `error`
(the tool raised) counts as a tool error.

## Metrics

A line that carries a metric also carries an `_aws` block in the CloudWatch Embedded Metric
Format. CloudWatch turns it into a metric in the `AfterWard` namespace, with one dimension,
`service`. No extra API calls are made.

| Metric | Unit | Written by |
|---|---|---|
| `chat_ms` | Milliseconds | agent, once per chat turn |
| `tool_ms` | Milliseconds | mcp, once per tool call |
| `tool_errors` | Count | mcp, 1 when a tool raises, otherwise 0 |
| `blocked_writes` | Count | agent, 1 per refused write |
| `upload_to_ready_ms` | Milliseconds | document_lambda, from the S3 upload event to a ready plan |

## Alarms

`infra/observability/template.yaml` is a CloudFormation template. **It is not deployed.** It defines:

- `afterward-tool-errors`: more than 3 tool errors in 5 minutes (the threshold is a parameter).
- `afterward-document-dlq-not-empty`: any message in `AfterWardDocumentProcessingDLQ`.
- An SNS topic for both alarms, with an optional email subscription.
- A new log group, `/afterward/bridge`, with 30-day retention.
- The three saved queries below.

To deploy later:

```
aws cloudformation deploy --region eu-west-2 --stack-name afterward-observability \
  --template-file infra/observability/template.yaml
```

Add the MCP server's ECS log group to the `QueryLogGroups` parameter so the saved queries search it.

## Saved Logs Insights queries

**Trace one request.** Paste the `request_id` from Developer view.

```
fields @timestamp, service, event, route, tool, kind, status, ms, reason, error_type, error_code
| filter request_id = "PASTE_REQUEST_ID_HERE"
| sort @timestamp asc
```

**Chat time, p50 and p90.** `kind` separates turns answered by code from turns answered by the model.

```
filter event = "agent_turn"
| stats count() as turns, pct(ms, 50) as p50_ms, pct(ms, 90) as p90_ms by bin(1h), kind
```

**Upload-to-ready time.**

```
filter event = "ingest_ready"
| stats count() as uploads, pct(upload_to_ready_ms, 50) as p50_ms, pct(upload_to_ready_ms, 90) as p90_ms, max(upload_to_ready_ms) as slowest_ms by bin(1d)
```

## Reading logs locally

The bridge and the local MCP server print the same lines to their terminals. To follow one turn:

```
python scripts/run_web_bridge.py | grep <request_id>
```
