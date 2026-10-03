from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.aws.s3_service import (
    download_document,
)

from app.ingestion.pdf_processor import (
    extract_text as extract_pdf_text,
)


KEY = (
    "patients/demo_patient_001/"
    "documents/s3_test_doc_001.pdf"
)

file_bytes = download_document(KEY)

pages = extract_pdf_text(
    file_bytes
)

print(
    "Pages:",
    len(pages)
)

for page in pages:
    print(
        "\nPAGE",
        page["page"]
    )

    print(
        page["text"][:500]
    )
