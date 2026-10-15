"""Upload the sample PDF to S3 with the fixed force_failure ID; current source no longer forces a failure."""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.test_letters import DEFAULT_TEST_LETTER
from app.aws.s3_service import (
    upload_document,
)


PATIENT_ID = "demo_patient_001"

# Change this to the PDF you want to test.
FILE_PATH = str(DEFAULT_TEST_LETTER)


# TEMPORARY: matches the forced failure used to test SQS retries and the DLQ.
document_id = "force_failure"


result = upload_document(
    file_path=FILE_PATH,
    patient_id=PATIENT_ID,
    document_id=document_id,
)


print("Uploaded successfully")
print("Patient ID:", PATIENT_ID)
print("Document ID:", document_id)
print("S3 key:", result["key"])
