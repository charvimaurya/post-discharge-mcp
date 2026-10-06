"""Extract the sample PDF with the canonical Bedrock schema and print the raw result."""

from pathlib import Path
import json
import sys

# Allow direct execution from scripts/ as well as module execution.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.ingestion.pdf_processor import (
    extract_text,
)

from app.ingestion.pipeline import (
    combine_pages,
)

from app.ingestion.bedrock import (
    invoke_extraction_model,
)


PDF_PATH = PROJECT_ROOT / "test_data" / "doc_001.pdf"


file_bytes = Path(
    PDF_PATH
).read_bytes()


pages = extract_text(
    file_bytes
)


text = combine_pages(
    pages
)


result = invoke_extraction_model(
    text
)


print(
    json.dumps(
        result,
        indent=2,
        default=str,
    )
)
