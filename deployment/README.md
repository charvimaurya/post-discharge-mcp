# Lambda deployment

Run commands from the project root with the virtual environment active.
Configuration files are now in this directory. AWS resource names remain
unchanged; the local archive uses the Afterward project name.

## Build

On a fresh checkout, install the pinned dependencies into an empty staging
directory (the existing staging directory was preserved during reorganization):

```bash
python -m pip install --target build/lambda_package -r deployment/requirements-lambda.txt
python -m scripts.deployment.build_document_lambda
```

The builder packages current source from `app/`, `models/`, `mcp_server/`, and
`lambdas/`, plus staged dependencies. It excludes cached bytecode and hidden
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
