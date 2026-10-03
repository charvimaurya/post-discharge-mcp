"""Split the local sample PDF into page-preserving text chunks and print previews without AWS calls."""

from pathlib import Path
import sys

# Direct execution puts this script folder on the import path; include project packages.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.ingestion.pdf_processor import (
    extract_text,
)

from app.rag.chunking import (
    chunk_document,
)


PDF_PATH = PROJECT_ROOT / "test_data" / "doc_001.pdf"


file_bytes = (
    Path(PDF_PATH)
    .read_bytes()
)


pages = extract_text(
    file_bytes
)


chunks = chunk_document(
    pages,
    document_id="rag_test_001",
)


print()
print(
    f"Pages: {len(pages)}"
)

print(
    f"Chunks: {len(chunks)}"
)


for chunk in chunks:

    print()
    print(
        "=" * 60
    )

    print(
        "Chunk ID:",
        chunk["chunk_id"]
    )

    print(
        "Page:",
        chunk["page"]
    )

    print()
    print(
        chunk["text"][:500]
    )
