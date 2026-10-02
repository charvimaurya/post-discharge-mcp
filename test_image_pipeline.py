from mcp_server.services.s3_service import upload_document
from app.ingestion.image_processor import extract_text_from_image
from app.ingestion.extractor import extract_recovery_information
from app.ingestion.normalizer import normalize_recovery_plan
from app.ingestion.validator import validate_recovery_plan
from app.ingestion.persistence import save_recovery_plan


IMAGE_PATH = "test_data/test_image1.jpeg"

PATIENT_ID = "demo_patient_001"

DOCUMENT_ID = "handwritten_discharge_001"


print("0. Uploading original document...")

s3_result = upload_document(
    file_path=IMAGE_PATH,
    patient_id=PATIENT_ID,
    document_id=DOCUMENT_ID
)

print(
    f"   Stored at: "
    f"{s3_result['bucket']}/"
    f"{s3_result['key']}"
)


print("1. Extracting image...")

pages = extract_text_from_image(
    IMAGE_PATH
)

print(f"   Extracted {len(pages)} page(s)")


print("2. Extracting recovery information...")

recovery_plan = extract_recovery_information(
    pages=pages,
    patient_id=PATIENT_ID,
    document_id=DOCUMENT_ID,
    source_type="image"
)


print("3. Normalizing...")

recovery_plan = normalize_recovery_plan(
    recovery_plan
)


print("4. Checking uncertainty...")

recovery_plan.has_unconfirmed_information = (
    any(
        medication.needs_confirmation
        for medication in recovery_plan.medications
    )
    or
    any(
        task.needs_confirmation
        for task in recovery_plan.tasks
    )
    or
    any(
        appointment.needs_confirmation
        for appointment in recovery_plan.appointments
    )
)


print(
    "   Has unconfirmed information:",
    recovery_plan.has_unconfirmed_information
)


print("5. Validating...")

valid, errors = validate_recovery_plan(
    recovery_plan
)


if not valid:

    print("\nValidation failed:")

    for error in errors:
        print(f" - {error}")

    raise SystemExit(1)


print("   Validation successful.")


print("6. Saving to DynamoDB...")

saved_plan = save_recovery_plan(
    recovery_plan
)


print("   Recovery State saved successfully.")


print("\n--- SUMMARY ---")

print(
    "Medications:",
    len(saved_plan["medications"])
)

print(
    "Tasks:",
    len(saved_plan["tasks"])
)

print(
    "Appointments:",
    len(saved_plan["appointments"])
)

print(
    "Needs confirmation:",
    saved_plan["has_unconfirmed_information"]
)
