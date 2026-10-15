"""Print text extracted from the local synthetic PDF without making AWS calls."""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.test_letters import DEFAULT_TEST_LETTER
from app.ingestion.pdf_processor import extract_text

pages = extract_text(str(DEFAULT_TEST_LETTER))

for page in pages:
    print(f"\n===== PAGE {page['page']} =====\n")
    print(page["text"])
