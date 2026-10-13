# Lambda deployment

Run commands from the project root with the virtual environment active.
Configuration files are in this directory. The document processor now uses
AfterWard resource names; see [the migration record](../docs/aws-name-migration.md).

## Build

The builder installs dependencies into fresh temporary staging using Linux
x86_64 wheels for the deployed Python 3.11 runtime. This works from macOS too.
Do not package your local virtual environment: native modules such as `rpds`
must match Lambda, not your laptop.

```bash
python -m scripts.deployment.build_document_lambda
```

The builder packages current source from `app/` (including `app/models/` and `app/mcp/`), and
`lambdas/`, plus the freshly installed Linux dependencies. It excludes cached bytecode and hidden
files. It produces `build/afterward_document_processor.zip` without deploying.
The pinned boto3/botocore versions include the S3 Vectors client used by RAG.
Build artifacts are excluded from Git. The previous ZIP is retained locally as
`build/afterward_document_processor.previous.zip`.

## Deploy when ready

```bash
aws lambda update-function-code --function-name AfterWardDocumentProcessor --zip-file fileb://build/afterward_document_processor.zip --region eu-west-2
aws lambda wait function-updated --function-name AfterWardDocumentProcessor --region eu-west-2
```

To apply environment settings separately:

```bash
aws lambda update-function-configuration --function-name AfterWardDocumentProcessor --environment file://deployment/lambda-env.json --region eu-west-2
```

That command replaces the function's environment-variable map. Include all
required settings in the file before applying it. Keep credentials out of it;
Lambda uses its execution role.

## Reminder checker (Phase 14)

The same ZIP also contains `lambdas/reminder_checker/handler.py`, so the
reminder Lambda reuses `build/afterward_document_processor.zip` with a
different handler. One EventBridge Scheduler entry wakes it every 5 minutes;
the selector reads each occurrence's own `clock_time`, so there is no
per-patient or per-item schedule. The scheduled input is `{}`: it never sends
`demo_now`, and `DEMO_FIXED_NOW` is not set, so it always uses real time.

Files:

- `reminder-env.json`: table names only.
- `reminder-policy.json`: RecoveryState `GetItem`/`UpdateItem`, EventHistory `Query`.
- `scheduler-trust-policy.json`, `scheduler-invoke-policy.json`: role that
  lets EventBridge Scheduler invoke only this function.
- `reminder-schedule-target.json`: schedule target with input `{}`.

Commands for recreating the existing reminder deployment:

```bash
aws iam create-role --role-name AfterwardReminderRole --assume-role-policy-document file://deployment/lambda-trust-policy.json
aws iam attach-role-policy --role-name AfterwardReminderRole --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
aws iam put-role-policy --role-name AfterwardReminderRole --policy-name AfterwardReminderTables --policy-document file://deployment/reminder-policy.json

aws lambda create-function --function-name AfterwardReminderChecker --runtime python3.11 --architectures x86_64 --handler lambdas.reminder_checker.handler.handler --role arn:aws:iam::<ACCOUNT_ID>:role/AfterwardReminderRole --timeout 30 --zip-file fileb://build/afterward_document_processor.zip --environment file://deployment/reminder-env.json --region eu-west-2

aws iam create-role --role-name AfterwardReminderSchedulerRole --assume-role-policy-document file://deployment/scheduler-trust-policy.json
aws iam put-role-policy --role-name AfterwardReminderSchedulerRole --policy-name InvokeReminderChecker --policy-document file://deployment/scheduler-invoke-policy.json

aws scheduler create-schedule --name afterward-reminder-checker --schedule-expression "rate(5 minutes)" --flexible-time-window Mode=OFF --target file://deployment/reminder-schedule-target.json --region eu-west-2
```

Update code later with `update-function-code` as above, using
`--function-name AfterwardReminderChecker`.

Manual test with a chosen time (never scheduled):

```bash
aws lambda invoke --function-name AfterwardReminderChecker --cli-binary-format raw-in-base64-out --payload '{"patient_id": "demo_patient_001", "demo_now": "2026-10-23T07:00:00+01:00"}' --region eu-west-2 /dev/stdout
```

`lambda-trust-policy.json` and `redrive-policy.json` retain their existing
contents for IAM and SQS setup. Their paths changed; no AWS resources were
modified by the reorganization.
