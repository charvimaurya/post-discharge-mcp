"""Read embedded PDF text from a file or bytes and return numbered pages."""

from io import BytesIO
from pathlib import Path
from pypdf import PdfReader


def extract_text(pdf_path: str | bytes, *, max_pages: int | None = None, max_text_chars: int | None = None) -> list[dict]:
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
    if reader.is_encrypted:
        raise ValueError("Encrypted PDF is not accepted")
    if max_pages is not None and len(reader.pages) > max_pages:
        raise ValueError("PDF page limit exceeded")
    pages = []
    total_chars = 0
    for page_number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        total_chars += len(text)
        if max_text_chars is not None and total_chars > max_text_chars:
            raise ValueError("PDF text limit exceeded")
        pages.append({"page": page_number, "text": text.strip()})
    return pages
