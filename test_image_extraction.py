from app.ingestion.image_processor import extract_text_from_image
from app.ingestion.extractor import extract_recovery_information


IMAGE_PATH = "test_data/test_image1.jpeg"

PATIENT_ID = "demo_patient_001"

DOCUMENT_ID = "handwritten_discharge_001"


print("1. Reading handwritten image...")

pages = extract_text_from_image(IMAGE_PATH)

print(f"   Extracted {len(pages)} page(s)")


print("2. Extracting structured recovery information...")

recovery_plan = extract_recovery_information(
    pages=pages,
    patient_id=PATIENT_ID,
    document_id=DOCUMENT_ID,
    source_type="image"
)


print("\n--- RECOVERY PLAN ---\n")

print(recovery_plan)