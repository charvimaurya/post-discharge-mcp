from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.ingestion.image_processor import extract_text_from_image


pages = extract_text_from_image(
    str(PROJECT_ROOT / "test_data" / "test_image1.jpeg")
)

print("\n--- EXTRACTED PAGES ---\n")

for page in pages:
    print(f"Page {page['page']}:")
    print(page["text"])