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

[The CloudFormation template](../infra/observability/template.yaml) defines:

- `afterward-tool-errors`: **more than 3** tool exceptions in 5 minutes by default, so 4 errors trigger it. It uses `AfterWard/tool_errors`, dimension `service=mcp`, statistic `Sum`. Expected tool rejections are not exceptions.
- `afterward-document-dlq-not-empty`: any **visible** message in `AfterWardDocumentProcessingDLQ`, using `AWS/SQS/ApproximateNumberOfMessagesVisible`, statistic `Maximum`, threshold greater than zero over 5 minutes. It does not measure in-flight messages.
- `afterward-mcp-no-healthy-targets`: fewer than one healthy MCP ALB target, or missing health metrics, over three one-minute evaluation periods. See availability coverage below.
- The SNS topic `afterward-alarms`, all three alarms' `AlarmActions`, and a topic policy permitting only these three CloudWatch alarms in this account to publish.
- An optional email subscription. Email delivery requires the recipient to confirm the subscription. With no confirmed subscriber, an alarm can fire without anyone receiving it.
- Three saved Logs Insights queries, including `/ecs/afterward-mcp` by default.

The tool-error and DLQ alarms treat missing data as `notBreaching`; the availability alarm deliberately uses `breaching`. An `OK` state alone does not prove log delivery, EMF extraction or document processing is working.

### MCP availability coverage

The simplest additional signal is the existing ALB's `AWS/ApplicationELB/HealthyHostCount`, with both `LoadBalancer` and `TargetGroup` dimensions. It needs no application changes, new health probes, Container Insights or custom metrics. `UnHealthyHostCount` alone is insufficient because deregistering every target can stop metric reporting without increasing unhealthy count. See [ALB CloudWatch metrics](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/load-balancer-cloudwatch-metrics.html).

The alarm uses `Minimum < 1`, period 60 seconds, three of three breaching datapoints, and missing data treated as breaching. Minimum is conservative across ALB nodes: it can alert when one node sees zero healthy targets even if another still serves traffic. It does not alert merely because one task fails while all nodes still see another healthy target. Require explicit ALB/target-group full-name parameters to avoid silently assuming a different deployment's identifiers.

Read-only AWS inspection on 17 October 2026 confirmed:

- `afterward-mcp-service` in `afterward-cluster` used task revision `afterward-mcp:5`, with desired/running count 1 and one healthy target on port 8000.
- ALB dimension: `app/afterward-mcp-alb/ddd2ba9b7ecf3836`.
- Target-group dimension: `targetgroup/afterward-mcp-tg/d1dcfea9428a3ae1`.
- Target-group HTTP health check: `/health`, traffic port 8000, success code 200, interval 30 seconds, timeout 5 seconds, unhealthy threshold 2 and healthy threshold 5.
- CloudWatch returned 15 recent one-minute datapoints for this exact dimension pair, each with minimum healthy count 1.
- Both CloudFront distributions were enabled and Deployed, pointing to this ALB. `E1G5Y3L9QK930` used an `https-only` origin policy; `E1SEY0O6MW9CTW` used `http-only`. Neither route was exercised by these metadata checks.
- No alarms with any of the three configured names were found in this account/region. No AWS resources were changed.

**Detects:** crashed or unreachable tasks, health-check timeouts/non-200 responses, and loss of all registered targets or sustained missing health metrics. It depends on ALB health-check detection before the alarm evaluation window. CloudWatch may use older real datapoints before filling missing periods, so three minutes is not a guaranteed outage-to-notification deadline. Missing telemetry or an incorrectly configured dimension can also trigger it; verify fresh datapoints before deployment. Intentional scale-to-zero or maintenance may alert.

**Does not detect:** authenticated MCP protocol failures, broken tool/backend dependencies while `/health` still returns 200, partial capacity loss with at least one healthy target visible to every node, or end-to-end failures involving CloudFront, viewer DNS/TLS, listeners, routing rules or authentication. The application's `/health` route returns a static service status and does not query DynamoDB, Bedrock or Secrets Manager. Short outages may recover before the alarm threshold. This is target-health monitoring, not a synthetic patient journey.

**Task 3 status: Implementation complete — awaiting deployment. Deployment status: unverified.** The changes below are local configuration only. No stack, log group, ECS revision or alarm transition was deployed or changed during this task. The read-only CloudFormation `ValidateTemplate` request was denied because the current AWS identity lacks `cloudformation:ValidateTemplate`. Local YAML/configuration tests do not replace service-side validation or notification delivery verification.

## AWS administrator runbook

These commands are instructions, not evidence of deployment. Run them only after approval, in the intended account and `eu-west-2`. Do not rename existing AWS resources.

### Prerequisites and preflight

1. Confirm the account with `aws sts get-caller-identity`. Confirm the existing cluster/service names, current ECS task-definition ARN, desired count, healthy task count and current log configuration. Save the previous task-definition ARN for rollback. Inspect any existing observability stack before updating it.
2. Verify the actual document-processing DLQ name and redrive policy. The template default is `AfterWardDocumentProcessingDLQ`; override it if the existing queue has another name. Do not create or rename a queue as part of this change.
3. Verify the ECS service target-group binding and ALB health-check settings using `ecs describe-services`, `elbv2 describe-target-groups` and `elbv2 describe-target-health`. Set required `McpLoadBalancerFullName` and `McpTargetGroupFullName` to the verified CloudWatch dimension values, not ARNs, DNS names or short names. Recheck them if infrastructure is replaced. Verify every `QueryLogGroups` entry exists. Defaults are `/aws/lambda/AfterWardDocumentProcessor` and `/aws/lambda/AfterwardReminderChecker`. Add the actual bridge group to this list only if it exists; otherwise chat-time queries will not include bridge/agent logs. The MCP group is added separately through `McpLogGroupName`.
4. Obtain an administrator-approved notification email and confirmation recipient. Check for naming conflicts with the topic and alarms before creating a stack. A previous version of this template owned `/afterward/bridge`; it had `DeletionPolicy: Retain`. Review the change set if migrating that stack. The current template creates **no log groups**.
5. The administrator needs CloudFormation validation/change-set/deployment permissions and permissions for the CloudWatch alarms, Logs Insights query definitions and SNS resources in this template. Separate log administration requires `logs:CreateLogGroup` and `logs:PutRetentionPolicy`. ECS rollout requires task-definition registration, service update and `iam:PassRole` for the existing task/execution roles. These are administrator permissions, not application task permissions.
6. Ensure the task can reach CloudWatch Logs through the existing network (NAT or a Logs VPC endpoint). Review the complete task definition against the live revision before registration; it contains unrelated environment/image settings that must not inadvertently replace newer production configuration.

Read-only preflight and template validation:

```bash
aws ecs describe-services --region eu-west-2 \
  --cluster afterward-cluster --services afterward-mcp-service \
  --query 'services[].{taskDefinition:taskDefinition,desired:desiredCount,running:runningCount}'
aws cloudformation validate-template --region eu-west-2 \
  --template-body file://infra/observability/template.yaml
```

### Administrator-managed log group and execution-role access

The administrator creates `/ecs/afterward-mcp` **before any new task starts** and sets **30-day retention**. The ECS definition does not set `awslogs-create-group`. The CloudFormation template does not create this group.

```bash
aws logs describe-log-groups --region eu-west-2 \
  --log-group-name-prefix /ecs/afterward-mcp \
  --query 'logGroups[].{name:logGroupName,retention:retentionInDays}'
# Only if the exact group does not exist:
aws logs create-log-group --region eu-west-2 --log-group-name /ecs/afterward-mcp
aws logs put-retention-policy --region eu-west-2 \
  --log-group-name /ecs/afterward-mcp --retention-in-days 30
```

The existing ECS **execution role**, `AfterWardEcsTaskExecutionRole`, needs the following log-write permissions. Substitute the verified account ID before applying through the administrator's IAM process. Keep its existing ECR and Secrets Manager permissions. Do not grant log-group creation to the application or execution role for this task.

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
    "Resource": "arn:aws:logs:eu-west-2:<ACCOUNT_ID>:log-group:/ecs/afterward-mcp:log-stream:*"
  }]
}
```

The [MCP task definition](../ecs-task-definition.json) uses `awslogs`, group `/ecs/afterward-mcp`, region `eu-west-2`, and stream prefix `mcp`. Streams have the form `mcp/afterward-mcp/<task-id>`. No application `cloudwatch:PutMetricData` permission is needed for EMF extraction from stdout.

### Execution-role verification result

On 17 October 2026, a read-only `iam:SimulatePrincipalPolicy` check for `AfterWardEcsTaskExecutionRole` returned **implicitDeny** for both `logs:CreateLogStream` and `logs:PutLogEvents` on a representative stream under `/ecs/afterward-mcp`. No policy was changed. This is a rollout blocker: the administrator must grant the scoped permissions above and repeat the check before registering/starting the new revision. A simulation is not an end-to-end log-delivery test and does not replace verification of network access, trust, permissions boundaries or organization policies.

Read-only verification command:

```bash
aws iam simulate-principal-policy \
  --policy-source-arn 'arn:aws:iam::<ACCOUNT_ID>:role/AfterWardEcsTaskExecutionRole' \
  --action-names logs:CreateLogStream logs:PutLogEvents \
  --resource-arns 'arn:aws:logs:eu-west-2:<ACCOUNT_ID>:log-group:/ecs/afterward-mcp:log-stream:mcp/afterward-mcp/predeploy-check' \
  --query 'EvaluationResults[].{Action:EvalActionName,Decision:EvalDecision}'
```

The reviewer needs `iam:SimulatePrincipalPolicy` for this check. The IAM administrator needs permission to inspect and amend the execution role's approved policies. Require `allowed` for both actions before rollout. Do not grant these administrator permissions to the application role.

### Approximate monitoring costs

For planning, allow approximately **US$5/month** for a small demo with at most 1 GB of additional logs/month, low query volume, three standard-resolution alarms, and a budget for up to six continuously emitted custom metric/service combinations (including both MCP timing/error metrics). This is an illustrative allowance, not a verified London quote or a spending cap. It excludes existing ECS, ALB, NAT/VPC endpoint and application costs, taxes, and currency conversion. Free-tier eligibility may reduce charges; do not depend on it.

AWS's published examples use roughly $0.10 per standard alarm/month and $0.30 per custom metric/month, giving about $2.10/month for these alarms and up to six metrics before logs. Add ingestion, retained compressed storage and Logs Insights scan charges at the current `eu-west-2` rates. SNS requests and email delivery are usage-based; small notification volumes usually contribute very little. Confirm the account's current rates using [CloudWatch pricing](https://aws.amazon.com/cloudwatch/pricing/), [SNS pricing](https://aws.amazon.com/sns/pricing/) and the [AWS Pricing Calculator](https://calculator.aws/).

Thirty-day retention limits stored logs, not ingestion charges. Repeated errors, broad queries and extra metric dimension combinations can exceed the allowance. Set a query time window and monitor actual billing after deployment. Saved query definitions do not run queries automatically. This task does not enable Container Insights or provision new networking.

### Review and deploy after approval

Create an unexecuted change set first. Replace the email placeholder, re-verify the observed ALB/target-group values below, and verify query groups before running:

```bash
aws cloudformation deploy --region eu-west-2 \
  --stack-name afterward-observability \
  --template-file infra/observability/template.yaml \
  --parameter-overrides AlarmEmail='<ADMIN_NOTIFICATION_EMAIL>' \
    McpLoadBalancerFullName='app/afterward-mcp-alb/ddd2ba9b7ecf3836' \
    McpTargetGroupFullName='targetgroup/afterward-mcp-tg/d1dcfea9428a3ae1' \
  --no-execute-changeset
```

Review the returned change-set ARN using `aws cloudformation describe-change-set`. For an existing stack, retain its previous template and parameters. After approval, execute that exact change set and wait for stack creation/update completion. Confirm the SNS subscription from the recipient's email.

Only after the log group, IAM access and complete task definition are approved:

```bash
aws ecs register-task-definition --region eu-west-2 \
  --cli-input-json file://ecs-task-definition.json \
  --query taskDefinition.taskDefinitionArn --output text
# Substitute the returned ARN, not a guessed revision:
aws ecs update-service --region eu-west-2 \
  --cluster afterward-cluster --service afterward-mcp-service \
  --task-definition '<NEW_TASK_DEFINITION_ARN>'
aws ecs wait services-stable --region eu-west-2 \
  --cluster afterward-cluster --services afterward-mcp-service
```

### Verify before marking deployed

- Check the running tasks use the approved revision and remain healthy. Inspect their task definition for the exact `awslogs` settings, and verify the log group's retention is 30 days.
- Inspect new `mcp/afterward-mcp/` streams using `aws logs describe-log-streams`, then check a new `tool_call` JSON/EMF record. Use an approved isolated synthetic patient for any tool invocation. Do not reset or write to shared Margaret or production records.
- Confirm `AfterWard/tool_errors` has dimension `service=mcp` using `aws cloudwatch list-metrics`. Confirm fresh datapoints using `get-metric-statistics` over the approved test window; metric listing alone does not prove current delivery.
- Run `aws cloudwatch describe-alarms --region eu-west-2 --alarm-names afterward-tool-errors afterward-document-dlq-not-empty afterward-mcp-no-healthy-targets` and compare thresholds, dimensions and SNS action ARN against the template. Check SNS topic policy and `list-subscriptions-by-topic`; the email subscription must have a real ARN, not `PendingConfirmation`.
- Before rollout, verify fresh `HealthyHostCount` datapoints with exactly the two configured dimensions. After deployment inspect the availability alarm state/history. Do not stop tasks, deregister targets, scale the shared service to zero or change health checks to test this alarm without separate approval; any fault test belongs in an approved isolated environment. Alarm actions only notify SNS and do not restart or scale ECS.
- Test topic delivery only after separate approval using a non-sensitive SNS test message. This tests delivery, not alarm evaluation. Validate alarm transitions in an isolated approved test environment. Do not inject failures or place messages into the live processing DLQ merely to test monitoring. Record alarm history, transition timestamps and receipt of notification for end-to-end evidence.
- Record stack ARN/status, task revision, log stream/time, metric datapoint/time, alarm action ARNs and confirmed subscription/delivery evidence. Until verified, report monitoring as configuration prepared, deployment unverified.

### Rollback

If new ECS tasks fail to start or deliver logs, update the service back to the **saved previous task-definition ARN** and wait for stability. Do not deregister the old revision in advance. Preserve logs for diagnosis.

For an unexecuted change set, delete that change set without executing it. For an existing stack update, allow CloudFormation's automatic rollback, then inspect events; do not delete an existing stack to recover an update. Restore its saved template/parameters through a reviewed change set if necessary. For a newly created stack only, an approved stack deletion removes its alarms, SNS subscriptions/topic and saved queries. Log groups are externally managed and remain. Do not delete the log group, purge the DLQ, restore indefinite retention or remove shared IAM permissions automatically.

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
python scripts/run_web_bridge.py | rg "PASTE_REQUEST_ID_HERE"
```

## Pre-deployment readiness review

Offline checks on 17 October 2026:

| Check | Result | Evidence or remaining action |
|---|---|---|
| CloudFormation schemas, intrinsics, references and SNS policy | PASS | cfn-lint 1.57.2, region eu-west-2, no findings. |
| ECS definition and awslogs options | PASS | Offline botocore request-schema check and configuration tests; no automatic log-group creation. |
| Tool-exception alarm | PASS | Matches the application's EMF namespace/dimension; four exceptions in a five-minute evaluation period trigger the default threshold. |
| MCP ALB target availability coverage | PASS | New HealthyHostCount alarm detects loss of healthy targets/missing telemetry; exact live dimensions and fresh metrics confirmed read-only. End-to-end CloudFront/MCP verification remains outside this signal. |
| Non-empty visible DLQ alarm | PASS | Correct AWS/SQS metric, QueueName dimension, Maximum statistic and threshold greater than zero. Live queue/redrive binding remains unverified. |
| SNS publishing policy | PASS | Restricted CloudWatch service principal, source account and exact three alarm ARNs. |
| Execution role effective log permissions | FAIL | Read-only IAM simulation returned implicitDeny for both required actions. Administrator remediation required before rollout. |
| Newly introduced credentials or broad IAM grants | PASS | Gitleaks scanned the tracked diff and new configuration test with no leaks; reviewed IAM grants have no wildcard actions. Existing account/resource ARNs are references, not credentials. |
| Regression checks and whitespace | PASS | 36 configuration/logging tests passed; git diff --check passed. |
| Order, retention, costs and rollback documentation | PASS | Administrator-managed group and permissions precede ECS rollout; reviewed change set precedes execution. |
| Service-side template validation | UNVERIFIED | Previous ValidateTemplate attempt was denied. Administrator must validate before deployment. |
| Live logs, EMF datapoints, alarm transitions and notification receipt | UNVERIFIED | No deployment or live state-changing tests performed. |

Local implementation is ready for administrator hand-off. **Do not execute the rollout until the execution-role permission failure and the remaining AWS preflight checks are resolved.** The implementation status is not evidence that monitoring is deployed or fully complete. No application-code changes are needed for the three configured alarms. End-to-end authenticated MCP/CloudFront monitoring remains a separate enhancement; live alarm transitions and notification delivery are unverified.
