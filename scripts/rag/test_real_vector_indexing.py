from pathlib import Path
import sys

# Direct execution puts this script folder on the import path; include project packages.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.ingestion.pdf_processor import (
    extract_text,
)

from app.rag.service import (
    index_document_pages,
)


PDF_PATH = PROJECT_ROOT / "test_data" / "doc_001.pdf"


file_bytes = (
    Path(PDF_PATH)
    .read_bytes()
)


pages = extract_text(
    file_bytes
)


count = index_document_pages(
    patient_id=
        "demo_patient_001",

    document_id=
        "rag_doc_001",

    pages=
        pages,
)


print(
    f"✅ Indexed {count} chunks"
)
