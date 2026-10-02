from pathlib import Path
from pprint import pprint

from app.database.recovery_state import save_recovery_state
from app.ingestion.pdf_processor import extract_text as extract_pdf_text
from app.ingestion.bedrock import invoke_extraction_model
from app.ingestion.normalizer import normalize_recovery_plan
from app.ingestion.validator import validate_recovery_plan


PDF_PATH = "test_data/discharge.pdf"

PATIENT_ID = "demo_patient_001"
DOCUMENT_ID = "phase4_pdf_test_001"


def combine_pages(pages: list[dict]) -> str:
    parts = []

    for page in pages:
        page_number = page["page"]
        text = page["text"]

        parts.append(
            f"[Page {page_number}]\n{text}"
        )

    return "\n\n".join(parts)


def main():

    # -----------------------------
    # 1. Read PDF
    # -----------------------------
    print("\n=== STEP 1: PDF EXTRACTION ===")

    file_bytes = Path(PDF_PATH).read_bytes()

    pages = extract_pdf_text(file_bytes)

    print(f"Pages extracted: {len(pages)}")

    for page in pages:
        print(
            f"\n--- PAGE {page['page']} ---"
        )
        print(page["text"][:500])

    # -----------------------------
    # 2. Combine page text
    # -----------------------------
    print("\n=== STEP 2: COMBINED TEXT ===")

    document_text = combine_pages(pages)

    print(document_text[:1000])

    # -----------------------------
    # 3. Bedrock extraction
    # -----------------------------
    print("\n=== STEP 3: BEDROCK OUTPUT ===")

    extracted = invoke_extraction_model(
        document_text
    )

    pprint(extracted)

    # -----------------------------
    # 4. Normalize
    # -----------------------------
    print("\n=== STEP 4: NORMALIZED STATE ===")

    state = normalize_recovery_plan(
        extracted=extracted,
        patient_id=PATIENT_ID,
        document_id=DOCUMENT_ID,
    )

    pprint(state)

    print(
        "\nStatus after normalization:",
        state.ingestion_status,
    )

    # -----------------------------
    # 5. Validate
    # -----------------------------
    print("\n=== STEP 5: VALIDATED STATE ===")

    state = validate_recovery_plan(
        state
    )

    save_recovery_state(state)
    print("\nRecovery State saved to DynamoDB")

    pprint(state)

    # -----------------------------
    # 6. Important checks
    # -----------------------------
    print("\n=== FINAL CHECKS ===")

    print(
        "Patient:",
        state.patient_id,
    )

    print(
        "Document:",
        state.document_id,
    )

    print(
        "Ingestion status:",
        state.ingestion_status,
    )

    print(
        "Pending check-in:",
        state.pending_checkin,
    )

    print(
        "Medications:",
        len(state.medications),
    )

    print(
        "Tasks:",
        len(state.tasks),
    )

    print(
        "Appointments:",
        len(state.appointments),
    )

    print(
        "Monitoring:",
        len(state.monitoring),
    )

    print(
        "Restrictions:",
        len(state.restrictions),
    )

    print(
        "Warning signs:",
        len(state.warning_signs),
    )

    # Show uncertainty flags
    print(
        "\n=== NEEDS CONFIRMATION ==="
    )

    for med in state.medications:
        print(
            "MED:",
            med.name,
            "needs_confirmation =",
            med.needs_confirmation,
        )

    for task in state.tasks:
        print(
            "TASK:",
            task.description,
            "needs_confirmation =",
            task.needs_confirmation,
        )

    for appointment in state.appointments:
        print(
            "APPOINTMENT:",
            appointment.with_,
            "needs_confirmation =",
            appointment.needs_confirmation,
        )


if __name__ == "__main__":
    main()
