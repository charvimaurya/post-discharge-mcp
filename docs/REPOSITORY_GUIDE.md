# Afterward: how to use this repository

Afterward reads discharge paperwork and turns it into:

1. **A recovery plan:** medications, tasks, appointments, restrictions, monitoring,
   and warning signs.
2. **Searchable source text:** passages from the original document that can help
   answer questions such as “What did my paperwork say about driving?”

The project was previously called CareLoop. GitHub uses **Afterward**, but the
existing AWS resources still have **CareLoop** names.

## Start here

You do not need to run every file. Most files are supporting code used by other files.

| What you want to do | Command |
|---|---|
| Check the automated tests | `pytest -v` |
| Read the sample PDF as plain text | `python -m scripts.ingestion.test_extraction` |
| Get structured JSON from the sample PDF | `python -m scripts.ingestion.test_phase3` |
| Get a normalized and validated recovery plan | `python run_ingestion.py` |
| Split the PDF into searchable pieces | `python -m scripts.rag.test_real_chunking` |
| Store those pieces in the vector index | `python -m scripts.rag.test_real_vector_indexing` |
| Search the stored text | `python -m scripts.rag.test_rag_search` |
| Test the complete deployed upload pipeline | `python -m scripts.ingestion.test_full_ingestion` |

**Run all commands from the project root**, with `.venv` active. Commands using
Bedrock, S3, DynamoDB, or S3 Vectors contact real AWS services and may cost money
or write data. Use the synthetic test documents.

### What “no single app server command” means

The document-processing and search components exist. They can run through local
scripts or the deployed Lambda. There is not yet one complete user-facing app
that connects document upload, questions, and medication/task completion.

**MCP server: not implemented.** The folder contains preliminary reader helpers,
but there is no complete running MCP server with registered application tools.

## 1. Set up your computer once

Use Python 3.11, matching the current Lambda runtime.

```bash
git clone https://github.com/charvimaurya/Afterward.git
cd Afterward
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install -r deployment/requirements-lambda.txt
python -m pip install pytest
```

If you already have the repository and `.venv`, start with:

```bash
source .venv/bin/activate
```

The second requirements file supplies the AWS SDK, including S3 Vectors support.
The two requirements files currently specify different python-dotenv versions;
installing in the order above uses the deployment version, 1.2.4. Pytest is
installed separately because it is not yet listed in these files.

### Add your settings

Create a file named `.env` in the project root. The current `.env.example` is
incomplete. This example points to the existing project resources:

```dotenv
AWS_REGION=eu-west-2
MODEL_MODE=test
TEST_MODEL_ID=eu.anthropic.claude-haiku-4-5-20251001-v1:0
FINAL_EXTRACTION_MODEL_ID=
FINAL_AGENT_MODEL_ID=
IMAGE_MODEL_ID=
DOCUMENT_BUCKET=careloop-documents-992617582533-london
PROCESSING_QUEUE_URL=https://sqs.eu-west-2.amazonaws.com/992617582533/CareLoopDocumentProcessing
RECOVERY_STATE_TABLE=PostDischargeRecoveryState
EVENT_HISTORY_TABLE=PostDischargeEventHistory
S3_VECTOR_BUCKET=careloop-vectors-992617582533-london
S3_VECTOR_INDEX=careloop-discharge-index
EMBEDDING_MODEL_ID=amazon.titan-embed-text-v2:0
EMBEDDING_DIMENSIONS=512
```

- Use your own resource names if you are working in another AWS account.
- Fill in `IMAGE_MODEL_ID` before running image tests.
- Keep `MODEL_MODE=test` for the configured development model. Final mode needs
  the relevant `FINAL_*` model IDs.
- Do not commit `.env` or AWS credentials.
- Settings already exported in your terminal take priority over `.env`.

### Check AWS access

For live tests, sign in using your normal AWS profile or login method. If you
use a named profile:

```bash
export AWS_PROFILE=your-profile
aws sts get-caller-identity
python check_setup.py
```

Use the actual profile name instead of `your-profile`. Omit the export when
using your default profile. The AWS CLI must be installed separately.

`check_setup.py` checks the account and creates AWS clients. It does **not** prove
that every model, bucket, or table is accessible.

## 2. Run tests in this order

### Step A — Check the code without running the live pipeline

```bash
pytest -v
```

At the last verified baseline: **93 passed, 7 deselected, 3 subtests passed**.
“Deselected” means the live AWS tests were intentionally left out.

If you have no AWS credentials configured, use dummy credentials for this
mocked test run only:

```bash
AWS_ACCESS_KEY_ID=testing AWS_SECRET_ACCESS_KEY=testing AWS_EC2_METADATA_DISABLED=true pytest -v
```

You still need region and bucket settings in `.env` because some modules read
configuration when imported. Never use dummy credentials for a live AWS test.

### Step B — Check the PDF text

```bash
python -m scripts.ingestion.test_extraction
```

Reads `test_data/doc_001.pdf` and prints its text. No AWS calls.
The current sample has **2 pages**. You may see pypdf `startxref` warnings;
the sample currently still extracts successfully.

### Step C — Check Bedrock extraction

```bash
python verify_models.py
python -m scripts.ingestion.test_phase3
```

The first command checks the configured extraction, agent, and embedding models.
The second sends PDF text to Bedrock and prints structured JSON.

Compare the JSON with the PDF: do the doses, dates, and instructions actually
appear in the source? Successful execution does not prove extraction accuracy.

To also normalize and validate the result:

```bash
python run_ingestion.py
```

This prints a `RecoveryState`, the Python object representing the patient's
recovery plan. **These local commands do not save it to DynamoDB or index it.**

### Step D — Check image extraction, if needed

```bash
python -m scripts.ingestion.test_image
python -m scripts.ingestion.test_phase3_image
```

The first transcribes `test_image1.jpeg`. The second also creates structured JSON.
Both need a working image model setting. Check handwritten numbers against the
image, even when the model does not mark them uncertain.

### Step E — Check document search

“RAG” here means finding relevant passages from the original paperwork.
An “embedding” is the numerical representation used to search by meaning.

Run in this order:

```bash
# Split the PDF locally; expect 2 pages and 4 chunks for the current fixture.
python -m scripts.rag.test_real_chunking

# Check the embedding model; expect 512 values.
python -m scripts.rag.test_embedding

# Create embeddings and write the document chunks to S3 Vectors.
python -m scripts.rag.test_real_vector_indexing

# Search the indexed text for driving instructions.
python -m scripts.rag.test_rag_search

# Check that patient 1 does not retrieve the second patient's test document.
python -m scripts.rag.test_patient_isolation
```

The vector bucket and index must already exist. The index dimensions must match
`EMBEDDING_DIMENSIONS`. Patient/document metadata must support filtering; see
[the AWS notes](aws-setup.md) and the current vector-store implementation.

Search returns source text, page numbers, document IDs, and distances. It does
not ask Claude to generate medical advice. The isolation script is a small
check, not a complete security assessment.

### Step F — Check the deployed pipeline

Do this after the earlier checks pass and the current Lambda is deployed:

```bash
python -m scripts.ingestion.test_full_ingestion
```

It uploads a PDF using a fresh document ID, then waits for that exact document's
state to become `ready` in DynamoDB. This changes live AWS data.

The deployed pipeline must already have working S3 notifications, SQS, Lambda,
DynamoDB, Bedrock, S3 Vectors, and permissions. A timeout means you should inspect
Lambda logs and queue state; it does not necessarily mean processing has stopped.

```bash
aws logs tail /aws/lambda/CareLoopDocumentProcessor --since 10m --region eu-west-2
```

Follow with the RAG search check to inspect retrieved evidence. A ready state
is not a substitute for checking the actual extracted content.

### Optional — Run live database and queue tests

```bash
pytest tests/database/test_phase5_actions.py -v -m integration
pytest tests/aws/test_sqs.py -v -m integration
```

These are intentionally excluded from normal `pytest -v`. They can complete
patient actions, write history, and receive queue messages. Use synthetic data.

## 3. Understand the workflow

### Local processing

```text
PDF or image
    ↓
pdf_processor.py or image_processor.py
    ↓
Numbered pages of text
    ↓
pipeline.py combines the pages
    ↓
bedrock.py extracts structured fields
    ↓
normalizer.py creates RecoveryState and its items
    ↓
validator.py flags missing or uncertain information
    ↓
RecoveryState returned to the caller
```

The local pipeline returns data. Its caller decides whether to save or index it.
`process_document_with_pages()` returns both the state and the original pages.

### Automatic processing after an upload

```text
Upload to S3
    ↓
S3 sends a notification to SQS
    ↓
Lambda handler.py receives the queue message
    ↓
document_service.py downloads and processes the file
    ↓
Save RecoveryState as "indexing"
    ↓
RAG service splits, embeds, and stores the original text
    ↓
Save RecoveryState as "ready"
```

If indexing fails, the state stays `indexing` and Lambda reports the failed
message. SQS can retry it. A repeat of the same `ready` document is skipped.
Retries currently repeat extraction too. AWS's special `s3:TestEvent` messages
are ignored because they are not document uploads.

### Searching and recording patient actions

```text
Question + patient ID
    ↓
Create query embedding
    ↓
Search vectors with a patient filter
    ↓
Return matching source passages
```

Medication/task completion is a separate path:

```text
Patient action
    ↓
Read and update RecoveryState
    ↓
Save it to DynamoDB
    ↓
Append an idempotent Event History entry
```

An idempotency key identifies an action so repeated requests can be recognized.
State saving and history writing are still separate operations, not one transaction.

## 4. Where to find things

| Folder | Plain-language purpose |
|---|---|
| `app/ingestion/` | Read documents and build recovery plans |
| `app/rag/` | Split, store, and search original document text |
| `app/aws/` | S3 and SQS helper functions |
| `app/database/` | Save/read plans and record patient actions |
| `models/` | Definitions of the data objects |
| `lambdas/` | Code AWS calls when a queue message arrives |
| `mcp_server/` | MCP server not implemented; preliminary helpers only |
| `scripts/` | Commands developers run manually |
| `tests/` | Automated tests run by pytest |
| `test_data/` | Synthetic PDFs and images |
| `deployment/` | AWS configuration and build instructions |
| `build/` | Generated files; kept out of Git |
| `docs/` | Guides and explanations |

The file-by-file reference below is for looking things up. You do not need to
read every row before running the tests.

### Repository structure at a glance

The notes beside each entry explain its purpose. `__init__.py` files mark Python
packages; they are not commands to run. Generated build contents are summarized
instead of listing every installed dependency.

```text
Afterward/
├── app/                              # Main application code
│   ├── __init__.py                    # Application package marker
│   ├── config.py                      # Read environment settings and select models
│   ├── aws/                           # S3 storage and SQS queue helpers
│   │   ├── __init__.py                 # Package marker
│   │   ├── s3_service.py               # Upload, download, and parse document keys
│   │   └── sqs_service.py              # Receive/delete messages and parse notifications
│   ├── database/                      # Current recovery plans and action history
│   │   ├── __init__.py                 # Package marker
│   │   ├── recovery_state.py           # Read/save plans and complete patient actions
│   │   └── event_history.py            # Write deduplicated events and read history
│   ├── ingestion/                     # Turn documents into structured recovery plans
│   │   ├── __init__.py                 # Package marker
│   │   ├── pdf_processor.py            # Extract numbered text pages from PDFs
│   │   ├── image_processor.py          # Transcribe images using Bedrock
│   │   ├── bedrock.py                  # Extract structured fields using a model/schema
│   │   ├── normalizer.py               # Convert extracted fields into data objects
│   │   ├── validator.py                # Flag missing and uncertain information
│   │   ├── pipeline.py                 # Connect extraction, normalization, validation
│   │   └── document_service.py         # Handle uploads, save plans, index text, retry failures
│   └── rag/                           # Store and search original document evidence
│       ├── __init__.py                 # Package marker
│       ├── chunking.py                 # Split page text into overlapping chunks
│       ├── embeddings.py               # Convert text into numerical search vectors
│       ├── vector_store.py             # Write/query S3 Vectors with patient filtering
│       └── service.py                  # Coordinate indexing and evidence retrieval
├── models/                            # Shared data definitions
│   ├── __init__.py                     # Package marker
│   └── recovery_model.py               # RecoveryState, instructions, and source evidence
├── lambdas/                           # Entry points run by AWS Lambda
│   └── document_processor/
│       ├── __init__.py                 # Package marker
│       └── handler.py                  # Receive SQS batches and report failed messages
├── mcp_server/                        # NOT IMPLEMENTED — complete MCP server is not available
│   ├── __init__.py                     # Package scaffolding
│   ├── server.py                       # Existing reader re-export; does not start a server
│   ├── services/
│   │   ├── __init__.py                 # Package scaffolding
│   │   └── dynamodb_service.py         # Existing DynamoDB table references
│   └── tools/
│       ├── __init__.py                 # Package scaffolding
│       └── get_recovery_plan.py        # Existing reader helper; not a registered MCP server
├── scripts/                           # Manual checks; some call/write to live AWS
│   ├── __init__.py                     # Allow python -m scripts... commands
│   ├── README.md                       # Manual command overview
│   ├── ingestion/                     # Test document processing
│   │   ├── __init__.py                 # Package marker
│   │   ├── test_extraction.py          # Read the local PDF text without AWS
│   │   ├── test_image.py               # Transcribe the sample image through Bedrock
│   │   ├── test_phase3.py              # PDF text → structured extraction JSON
│   │   ├── test_phase3_image.py        # Image transcription → structured JSON
│   │   ├── test_document_pages.py      # Process PDF and display original page previews
│   │   └── test_full_ingestion.py      # Upload fresh PDF and wait for its saved ready state
│   ├── rag/                           # Test chunking, indexing, and search
│   │   ├── __init__.py                 # Package marker
│   │   ├── test_real_chunking.py       # Split the local sample PDF; no AWS
│   │   ├── test_embedding.py           # Check live embedding dimensions and sample values
│   │   ├── test_vector_indexing.py     # Index hardcoded synthetic pages
│   │   ├── test_real_vector_indexing.py # Index the sample PDF in S3 Vectors
│   │   ├── test_vector_search.py       # Search driving evidence and show source details
│   │   ├── test_rag_search.py          # Similar search with shorter printed output
│   │   └── test_patient_isolation.py   # Check a second patient's document is excluded
│   ├── aws/                           # Manual storage, queue, and model diagnostics
│   │   ├── __init__.py                 # Package marker
│   │   ├── test_bedrock.py             # Hardcoded Nova connectivity check
│   │   ├── test_s3.py                  # Upload the sample image
│   │   ├── test_s3_config.py           # Print storage configuration
│   │   ├── test_s3_key_parser.py       # Parse an example document key
│   │   ├── test_s3_download_current.py # Download an existing fixed test key
│   │   ├── test_s3_to_pdf_processor.py # Download a PDF and extract its text
│   │   ├── test_s3_to_image_processor.py # Upload/download image and process its state
│   │   ├── test_s3_to_recovery_state.py # Process an S3 PDF and save to DynamoDB
│   │   ├── upload_test_document.py     # Upload PDF using the existing force_failure ID
│   │   ├── check_s3_to_sqs.py          # Upload a file and look for its queue notification
│   │   └── diagnose_s3_sqs.py          # Inspect configuration and test queue connectivity
│   └── deployment/
│       ├── __init__.py                 # Package marker
│       └── build_document_lambda.py   # Build a ZIP from source and staged dependencies
├── tests/                             # Automated checks discovered by pytest
│   ├── README.md                       # Test commands and integration-test explanation
│   ├── test_model_config.py            # Model selection and invalid/missing settings
│   ├── sample_discharge.txt            # Supplemental text fixture
│   ├── ingestion/
│   │   ├── test_document_pipeline.py  # Routing and save/index ordering
│   │   ├── test_document_worker.py    # Lambda behavior and retry failures
│   │   ├── test_phase4.py             # Normalization and confirmation flags
│   │   ├── test_source_evidence.py    # Preserve source page/snippet information
│   │   └── test_validator.py          # Preserve content and flag uncertainty
│   ├── database/
│   │   └── test_phase5_actions.py     # State, completion actions, and event idempotency
│   ├── rag/
│   │   └── test_rag_chunking.py        # Chunk splitting and page information
│   └── aws/
│       └── test_sqs.py                 # Notification parsing; optional live queue test
├── test_data/                         # Synthetic documents used by manual checks
│   ├── doc_001.pdf                     # Sample two-page discharge PDF
│   ├── test_image1.jpeg                # Sample image for transcription
│   └── test_image2.jpeg                # Additional image fixture
├── deployment/                        # Settings used when building/deploying Lambda
│   ├── README.md                       # Build and deployment instructions
│   ├── lambda-env.json                 # Lambda environment-variable map
│   ├── lambda-trust-policy.json        # Role trust-policy configuration
│   ├── redrive-policy.json             # Queue/DLQ retry configuration
│   └── requirements-lambda.txt         # Pinned Lambda dependencies
├── build/                             # Generated local files; excluded from Git
│   ├── lambda_package/                # Staged runtime dependencies
│   ├── afterward_document_processor.zip # Current build output
│   └── careloop_document_processor.previous.zip # Previous ZIP, when present
├── docs/                              # Developer documentation
│   ├── REPOSITORY_GUIDE.md             # This setup, workflow, and file guide
│   ├── architecture.md                 # Concise design and component relationships
│   ├── testing.md                      # Short testing reference
│   └── aws-setup.md                    # AWS configuration and troubleshooting
├── README.md                          # Project overview and documentation links
├── requirements.txt                   # Base Python dependencies
├── pytest.ini                         # Test discovery and default integration exclusions
├── .env                               # Local settings; excluded from Git
├── .env.example                       # Incomplete configuration template
├── .gitignore                         # Keep secrets, caches, and builds out of Git
└── output.txt                         # Index pointing to maintained documentation
```

The MCP folder contains preliminary helpers, but the **MCP server is not
implemented**. A running server with registered recovery-plan, retrieval, and
patient-action tools still needs to be built. Root utility scripts are omitted
from this tree, as requested earlier; their relevant run commands remain above.

## 5. File-by-file reference


All `__init__.py` files mark Python packages; they are not commands to run.

### Core application

| File | Responsibility |
|---|---|
| `app/config.py` | Environment configuration, model selection, table/bucket/queue/vector settings |
| `app/aws/s3_service.py` | Upload/download bytes, supported upload extensions, document-key creation/parsing |
| `app/aws/sqs_service.py` | Receive/delete messages and parse S3 notifications |
| `app/database/recovery_state.py` | Save dataclass/dictionary state; read state, medications, tasks; record completion actions |
| `app/database/event_history.py` | Stable idempotency-key helper, conditional event writes, event reader |
| `models/recovery_model.py` | RecoveryState, Medication, Task, Appointment, Monitoring, and Source dataclasses |
| `app/ingestion/pdf_processor.py` | Extract embedded PDF text into numbered pages with pypdf |
| `app/ingestion/image_processor.py` | Bedrock image transcription and uncertainty preservation |
| `app/ingestion/bedrock.py` | Extraction schema, prompt, Converse call, structured tool-output parsing, usage/stop logging |
| `app/ingestion/normalizer.py` | Clean and map extraction dictionaries to dataclasses, IDs, and source evidence |
| `app/ingestion/validator.py` | Flag uncertain/missing item fields; return validated state |
| `app/ingestion/pipeline.py` | File-type dispatch, page combination, reusable extraction/normalization/validation orchestration |
| `app/ingestion/document_service.py` | SQS/S3 event orchestration, duplicate check, persistence, RAG indexing |
| `app/rag/chunking.py` | Page-preserving overlapping text chunks and deterministic chunk IDs |
| `app/rag/embeddings.py` | Titan embedding requests and dimension checks |
| `app/rag/vector_store.py` | S3 Vectors writes and patient-filtered queries |
| `app/rag/service.py` | Coordinate indexing and return search evidence |
| `lambdas/document_processor/handler.py` | SQS batch entry point and per-message failure reporting |

### Manual script reference

Use `python -m scripts.<group>.<filename_without_py>`.

| Group/file | Purpose and prerequisite |
|---|---|
| `ingestion/test_extraction.py` | Local sample PDF text; no AWS |
| `ingestion/test_image.py` | Sample image transcription; Bedrock |
| `ingestion/test_phase3.py` | PDF → extraction JSON; Bedrock |
| `ingestion/test_phase3_image.py` | Image transcription → extraction JSON; Bedrock |
| `ingestion/test_document_pages.py` | Process sample PDF while preserving/printing original pages |
| `ingestion/test_full_ingestion.py` | Upload fresh document and poll its saved state; full deployed infrastructure |
| `rag/test_embedding.py` | One embedding, length and first values |
| `rag/test_real_chunking.py` | Local PDF chunk/page previews |
| `rag/test_vector_indexing.py` | Index hardcoded synthetic pages |
| `rag/test_real_vector_indexing.py` | Index current PDF pages |
| `rag/test_vector_search.py` | Driving evidence lookup with document/page/distance |
| `rag/test_rag_search.py` | Similar driving lookup with shorter output |
| `rag/test_patient_isolation.py` | Index second patient fixture, search as first patient, reject second document |
| `aws/test_bedrock.py` | Separate hardcoded Nova smoke test, not the MODEL_MODE extraction selector |
| `aws/test_s3_config.py` | Inspect S3-related settings |
| `aws/test_s3_key_parser.py` | Parse example document keys |
| `aws/test_s3.py` | Upload the test image |
| `aws/test_s3_download_current.py` | Download fixed s3_test_doc_001.pdf key; object must already exist |
| `aws/test_s3_to_pdf_processor.py` | Same fixed object → local PDF page text |
| `aws/test_s3_to_recovery_state.py` | Fixed PDF object → local pipeline → DynamoDB save; no local RAG indexing |
| `aws/test_s3_to_image_processor.py` | Upload/download image and locally process state; no explicit database save |
| `aws/upload_test_document.py` | Upload sample PDF; currently still uses document_id=force_failure |
| `aws/check_s3_to_sqs.py` | Upload fresh PDF and poll for its notification |
| `aws/diagnose_s3_sqs.py` | Inspect configuration and exercise queue diagnostics; may send test messages |
| `deployment/build_document_lambda.py` | Build local ZIP from source and staged dependencies; no deployment |

The temporary force_failure exception has been removed from current source.
The upload script's old ID does not itself force a failure. Prefer the full
integration script with a fresh ID for normal testing. Fixed S3 download keys
are not automatically created by the fresh-ID uploader; edit their constants
or upload a matching object before running them.

### Automated tests

| File | Coverage |
|---|---|
| `tests/test_model_config.py` | Model mode selection and missing settings |
| `tests/ingestion/test_document_pipeline.py` | Routing, extraction boundaries, state-save/index ordering |
| `tests/ingestion/test_document_worker.py` | Handler, indexing retries, duplicate skip, final-save failure |
| `tests/ingestion/test_phase4.py` | Normalization/validation and confirmation behavior |
| `tests/ingestion/test_source_evidence.py` | Extraction schema and normalized source provenance |
| `tests/ingestion/test_validator.py` | Uncertainty and content preservation with current dataclasses |
| `tests/database/test_phase5_actions.py` | State reads/writes, action completion, idempotent history; optional live tests |
| `tests/aws/test_sqs.py` | S3/SQS message parsing; optional live queue check |
| `tests/rag/test_rag_chunking.py` | Chunking behavior |
| `tests/sample_discharge.txt` | Supplemental text fixture |
| `test_data/doc_001.pdf` | Fictional two-page discharge fixture |
| `test_data/test_image1.jpeg`, `test_image2.jpeg` | Image transcription fixtures |

### Deployment and documentation

| Path | Purpose |
|---|---|
| `deployment/lambda-env.json` | Environment map to apply explicitly to Lambda |
| `deployment/lambda-trust-policy.json` | Lambda role trust-policy document |
| `deployment/redrive-policy.json` | SQS DLQ/redrive configuration |
| `deployment/requirements-lambda.txt` | Pinned staged runtime dependencies |
| `deployment/README.md` | Build and deployment commands |
| `build/lambda_package/` | Local staged dependencies; ignored by Git |
| `build/afterward_document_processor.zip` | Current generated deployment ZIP |
| `build/careloop_document_processor.previous.zip` | Locally preserved old ZIP, when present |
| `README.md` | Project overview and documentation links |
| `docs/architecture.md` | Concise architecture and limitations |
| `docs/testing.md` | Short testing command reference |
| `docs/aws-setup.md` | Existing resources and troubleshooting |
| `scripts/README.md`, `tests/README.md` | Group-specific command references |

## 6. Build and deploy when ready

Building creates a ZIP on your computer. Deploying uploads that ZIP to Lambda.
They are different steps.

On a fresh checkout, prepare the dependencies, then build:

```bash
python -m pip install --target build/lambda_package -r deployment/requirements-lambda.txt
python -m scripts.deployment.build_document_lambda
```

The ZIP is `build/afterward_document_processor.zip`. The builder does not deploy
anything or create AWS resources. See [deployment/README.md](../deployment/README.md)
for the upload and environment-update commands.

Check `deployment/lambda-env.json` before deploying. Updating Lambda's environment
replaces its entire settings map. `.env` is not included in the ZIP; add
`IMAGE_MODEL_ID` to the Lambda settings if you need image ingestion.

After deployment, run the full-ingestion test from Step F.

## 7. Common problems and important limits

| What you see | What to check |
|---|---|
| `No module named app` | Run from the project root using the documented `python -m ...` command |
| Missing PDF | The current file is `test_data/doc_001.pdf`, not `discharge.pdf` |
| S3 `NoSuchKey` | The object key hardcoded in that script may not exist in the bucket |
| Bedrock `AccessDenied` | Check the AWS identity, model access/subscription, and permissions |
| Empty or cut-off extraction | Inspect `BEDROCK_STOP_REASON` and `BEDROCK_USAGE` in logs |
| Full-ingestion timeout | Check Lambda logs, its deployed code/configuration, and SQS state |
| Old state says ready but search finds nothing | Older ready records are not automatically repaired by the retry fix |

A few scripts need extra care:

- `aws/upload_test_document.py` still uses the old `force_failure` document ID.
  Current source no longer has the forced exception. Use the full-ingestion
  script's fresh IDs for normal tests.
- Fixed-key download scripts need their named S3 object to exist first.
- Upload scripts may trigger the deployed pipeline through S3 notifications.
- Queue diagnostic scripts compete with Lambda for messages. Avoid polling SQS
  manually while testing the complete pipeline.
- Do not import manual test scripts into other code: several execute AWS calls
  immediately when imported.

Remaining software limitations:

- Vector keys currently use document/page/chunk IDs, not patient IDs. Use unique
  document IDs across patients until that collision risk is fixed.
- A retry can repeat Bedrock calls. The retry fix does not solve concurrent or
  out-of-order document updates.
- Medication/task dates are still descriptive text, not fully parsed schedules.
- Event History reads return one query page. Use recorded_at for actual event
  time; the deterministic sort key is not necessarily chronological.
- Automated tests check software behavior. They do not prove medical accuracy.

For more detail, see [architecture](architecture.md), [testing](testing.md), and
[AWS setup](aws-setup.md). This guide does not itself deploy or modify AWS resources.
