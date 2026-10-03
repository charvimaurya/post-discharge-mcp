# Manual checks

Run commands from the project root with the virtual environment active.
Automated tests live in `tests/`; these scripts are manual checks and may call
AWS, incur usage charges, or write data depending on the script.

The former root-level `test_*.py` scripts are now grouped here:

- `ingestion/`: PDF text, image transcription, and structured extraction checks.
- `aws/`: Bedrock connectivity and S3 upload/download checks.
- `rag/`: Embeddings, chunking, vector indexing/search, and patient-isolation checks.
- `deployment/`: Lambda deployment package builder.

Examples:

```bash
python -m scripts.ingestion.test_extraction
python -m scripts.ingestion.test_phase3
python -m scripts.ingestion.test_phase3_image
python -m scripts.aws.test_bedrock
python -m scripts.aws.test_s3_key_parser
python -m scripts.rag.test_real_chunking
python -m scripts.rag.test_vector_search
python -m scripts.ingestion.test_full_ingestion
python -m scripts.aws.check_s3_to_sqs
python -m scripts.deployment.build_document_lambda
```

Direct paths also work, for example `python scripts/ingestion/test_phase3.py`.
S3 download checks still require their configured object keys to exist.

All manual scripts previously directly under `scripts/` now live in the groups
above. Update saved commands to include the group name. The Lambda builder
reads staged dependencies from `build/lambda_package/` and writes
`build/afterward_document_processor.zip`; it does not deploy it.
See [deployment setup](../deployment/README.md) to install the pinned dependencies.
