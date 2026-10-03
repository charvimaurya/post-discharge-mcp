"""Read embedded PDF text from a file or bytes and return numbered pages."""

from io import BytesIO
from pathlib import Path
from pypdf import PdfReader


def extract_text(pdf_path: str | bytes) -> list[dict]:
    """
    Extract embedded text from a PDF file path or PDF bytes.

    Returns a list of {"page": int, "text": str}.
    Page numbers start at 1. Pages without embedded text return an empty
    string; scanned/image-only pages require separate image processing.
    """
    if isinstance(pdf_path, bytes):
        reader = PdfReader(BytesIO(pdf_path))
    else:
        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")
        reader = PdfReader(str(path))
    pages = []
    for page_number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append({"page": page_number, "text": text.strip()})
    return pages
