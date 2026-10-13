# AWS setup and troubleshooting

Runtime settings come from app/config.py. Local scripts read .env; Lambda uses
its configured environment. Editing deployment/lambda-env.json does not itself
update AWS. Never put AWS credentials in committed configuration files.

Existing resource identifiers (not renamed during repository cleanup):

- Region: eu-west-2
- Document bucket: afterward-documents-<ACCOUNT_ID>-london
- Processing queue: AfterWardDocumentProcessing
- Dead-letter queue: AfterWardDocumentProcessingDLQ
- Lambda: AfterWardDocumentProcessor
- Recovery table: PostDischargeRecoveryState (patient_id partition key)
- History table: PostDischargeEventHistory (patient_id partition key, timestamp sort key)
- Vector bucket: afterward-vectors-<ACCOUNT_ID>-london
- Vector index: afterward-discharge-index

MODEL_MODE selects test or final model settings. Image transcription uses
IMAGE_MODEL_ID. Titan embedding settings use EMBEDDING_MODEL_ID and
EMBEDDING_DIMENSIONS (512 in the current configuration).

DOCUMENT_BUCKET is preferred; AFTERWARD_BUCKET is also
fallbacks. PROCESSING_QUEUE_URL is the queue setting, with legacy aliases in config.

## Deployment

Follow ../deployment/README.md. Build current source with:

```bash
python -m scripts.deployment.build_document_lambda
```

The archive is build/afterward_document_processor.zip. The handler is
lambdas.document_processor.handler.lambda_handler. Bundle app/models/ and the
current S3 Vectors-capable SDK dependencies. Enable ReportBatchItemFailures on
the SQS event-source mapping so failed records are retried individually.

## Common issues

- ModuleNotFoundError locally: run manual checks with python -m scripts.<group>.<name>.
- Missing models in Lambda: rebuild using the maintained builder, not an old ZIP.
- Bedrock Marketplace AccessDenied: an authorized AWS identity must enable model
  access. Complete the Anthropic use-case form if requested. After permission
  changes, follow the delay suggested in the AWS error before retrying.
- Empty/truncated structured extraction: inspect BEDROCK_STOP_REASON and
  BEDROCK_USAGE. Raw document extraction is not logged by the pipeline.
- Vector indexing failure: the worker now leaves state at indexing and reports
  the failed SQS message. A retry reruns the pipeline; ready is saved only after
  indexing succeeds. Previously saved ready records need explicit reprocessing
  if their vectors are missing.

AWS resources have not been migrated to Afterward names. The earlier migration
attempt was blocked by IAM inspection permissions. Repository cleanup does not
change IAM policies, queue configuration, or deployed Lambda code.

Model access reference: https://docs.aws.amazon.com/bedrock/latest/userguide/model-access.html
