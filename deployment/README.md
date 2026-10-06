# Lambda deployment

Run commands from the project root with the virtual environment active.
Configuration files are now in this directory. AWS resource names remain
unchanged; the local archive uses the Afterward project name.

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
`build/careloop_document_processor.previous.zip`.

## Deploy when ready

```bash
aws lambda update-function-code --function-name CareLoopDocumentProcessor --zip-file fileb://build/afterward_document_processor.zip --region eu-west-2
aws lambda wait function-updated --function-name CareLoopDocumentProcessor --region eu-west-2
```

To apply environment settings separately:

```bash
aws lambda update-function-configuration --function-name CareLoopDocumentProcessor --environment file://deployment/lambda-env.json --region eu-west-2
```

That command replaces the function's environment-variable map. Include all
required settings in the file before applying it. Keep credentials out of it;
Lambda uses its execution role.

`lambda-trust-policy.json` and `redrive-policy.json` retain their existing
contents for IAM and SQS setup. Their paths changed; no AWS resources were
modified by the reorganization.
