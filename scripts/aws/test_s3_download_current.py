"""Download a fixed test-document key from S3 and print its byte count; the object must exist."""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.aws.s3_service import (
    download_document,
)


KEY = (
    "patients/demo_patient_001/"
    "documents/s3_test_doc_001.pdf"
)

file_bytes = download_document(KEY)

print(
    "Downloaded bytes:",
    len(file_bytes),
)