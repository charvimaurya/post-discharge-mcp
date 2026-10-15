"""Process the sample PDF with Bedrock while printing the returned patient ID and original page previews."""

from pathlib import Path
import sys

# Direct execution puts this script folder on the import path; include project packages.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.test_letters import DEFAULT_TEST_LETTER
from app.ingestion.pipeline import (
    process_document_with_pages,
)


PDF_PATH = DEFAULT_TEST_LETTER


file_bytes = (
    Path(PDF_PATH)
    .read_bytes()
)


state, pages = (
    process_document_with_pages(
        file_bytes=file_bytes,
        filename=PDF_PATH.name,
        patient_id="demo_patient_001",
        document_id="page_test_001",
    )
)


print()
print("RECOVERY STATE:")
print(
    state.patient_id
)

print()
print("PAGES:")
print(
    f"Number of pages: {len(pages)}"
)


for page in pages:

    print()
    print(
        f"PAGE {page['page']}"
    )

    print(
        page["text"][:300]
    )
