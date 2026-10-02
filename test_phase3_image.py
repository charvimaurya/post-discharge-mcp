import json
from app.ingestion.image_processor import extract_text_from_image as extract_image_text
from app.ingestion.bedrock import invoke_extraction_model
from app.ingestion.pipeline import combine_pages

# --- point this at your handwritten note image ---
IMAGE_PATH = "test_data/test_image1.jpeg"   # <-- change to your actual image path

# 1. Get page text from the image (via Bedrock Nova transcription)
pages = extract_image_text(IMAGE_PATH)
print(f"Transcribed {len(pages)} page(s) from image\n")

# 2. Show the raw transcription first — this is the risky step, look at it
for p in pages:
    print(f"--- page {p['page']} raw transcription ---")
    print(p["text"])
    if p.get("uncertain"):
        print("  [flagged: contains unreadable/uncertain text]")
    print()

# 3. Join and run extraction
document_text = combine_pages(pages)
if not document_text.strip():
    raise SystemExit("No text transcribed from image.")

result = invoke_extraction_model(document_text)

# 4. Show structured result
print("--- extracted structure ---")
print(json.dumps(result, indent=2))

for key in ["discharge_date", "medications", "tasks", "appointments",
            "restrictions", "monitoring", "warning_signs"]:
    assert key in result, f"MISSING KEY: {key}"
print(f"\nOK — all 7 fields present. meds={len(result['medications'])}")
