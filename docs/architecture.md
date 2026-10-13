# Architecture

Afterward is a post-discharge companion prototype. Active document storage, queues, and processing use AfterWard resource names.
The original CareLoop resources are retained for rollback.

## Document ingestion

S3 upload -> SQS -> `lambdas/document_processor/handler.py` ->
`app/ingestion/document_service.py` -> download ->
`process_document_with_pages()` -> RecoveryState and original pages.

The reusable pipeline extracts text using pypdf for text PDFs or Bedrock for
images, combines page text, calls structured extraction in `bedrock.py`, then
normalizes and validates the result. Dataclasses live in `app/models/recovery_model.py`.
Source snippets and page numbers preserve evidence where available.

The worker saves the validated state with `ingestion_status="indexing"`, indexes
original pages through `app/rag/service.py`, then saves `ingestion_status="ready"`.
Only a matching ready document is skipped on repeat delivery. Indexing or final
save failures propagate to the handler, which returns the SQS message ID in
`batchItemFailures`. S3 notification test events are ignored.

Retries currently rerun extraction and indexing. This is not a transaction or a
concurrency lock. Records already marked ready before this change are not
backfilled automatically. Local pipeline validation still returns ready; the
worker owns the extra indexing stage for asynchronous ingestion.

## RAG

`app/rag/` contains page-preserving chunking, Titan embeddings, S3 Vectors access,
and search orchestration. Retrieval filters on patient_id and returns evidence,
not generated medical advice. The configured embedding dimensions must match
the vector index. Chunk keys currently derive from document/page/chunk IDs;
use unique document IDs across patients to avoid collisions in the shared index.

## Storage and interfaces

- `app/aws/`: S3 upload/download/key parsing and SQS helpers.
- `app/database/`: current RecoveryState and Event History operations.
- `app/mcp/tools/recovery.py`: recovery-plan reader; server.py re-exports it.
- `app/models/`: shared typed state, including the patient timezone.

Medication/task readers return current lists; date arguments do not implement
occurrence filtering. State updates and history writes are separate operations.
The event idempotency helper provides deterministic keys, not a cross-service
transaction.

## Repository layout

`tests/` holds automated tests grouped by area. `scripts/` holds manual checks.
`test_data/` contains synthetic fixtures. `deployment/` contains configuration
and dependency pins; ignored `build/` contains staged dependencies and archives.
