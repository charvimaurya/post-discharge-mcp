"""Extract sample PDF text, request structured JSON from Bedrock, and check the top-level fields."""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import json
from app.ingestion.pdf_processor import extract_text
from app.ingestion.bedrock import invoke_extraction_model
from app.ingestion.pipeline import combine_pages

# --- point this at your test PDF ---
PDF_PATH = str(PROJECT_ROOT / "test_data" / "doc_001.pdf")   # <-- change to your actual PDF path

# 1. Get page text from the PDF
pages = extract_text(PDF_PATH)
print(f"Extracted {len(pages)} page(s) from PDF\n")

# 2. Join pages into one document string
document_text = combine_pages(pages)

if not document_text.strip():
    raise SystemExit(
        "No text found in PDF. If this is a scanned/handwritten doc, "
        "run it through the image processor instead."
    )

# 3. Run extraction
result = invoke_extraction_model(document_text)

# 4. Show the structured result
print(json.dumps(result, indent=2))

# 5. Quick shape check (Phase 3 'done when')
for key in ["discharge_date", "medications", "tasks", "appointments",
            "restrictions", "monitoring", "warning_signs"]:
    assert key in result, f"MISSING KEY: {key}"

print(f"\nOK — all 7 fields present. "
      f"meds={len(result['medications'])}, "
      f"tasks={len(result['tasks'])}, "
      f"appointments={len(result['appointments'])}")
