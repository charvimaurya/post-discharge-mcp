"""Process the sample PDF, save its RecoveryState to DynamoDB, and print the stored summary."""

from pathlib import Path
import sys

# Support direct execution from scripts/ without requiring package installation.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.ingestion.pipeline import (
    process_document,
)

from app.database.recovery_state import (
    save_recovery_state,
    get_recovery_state,
)


PDF_PATH = PROJECT_ROOT / "test_data" / "doc_001.pdf"


patient_id = "demo_patient_001"

document_id = "new_schema_db_001"


file_bytes = Path(
    PDF_PATH
).read_bytes()


print(
    "Processing document..."
)


state = process_document(
    file_bytes=file_bytes,
    filename="doc_001.pdf",
    patient_id=patient_id,
    document_id=document_id,
)


print(
    "Saving RecoveryState..."
)


save_recovery_state(
    state
)


print(
    "Reading RecoveryState..."
)


saved = get_recovery_state(
    patient_id
)


print(
    "Document ID:",
    saved.get("document_id"),
)

print(
    "Status:",
    saved.get("ingestion_status"),
)

print(
    "Medications:",
    len(
        saved.get(
            "medications",
            []
        )
    ),
)

print(
    "Tasks:",
    len(
        saved.get(
            "tasks",
            []
        )
    ),
)

print(
    "Appointments:",
    len(
        saved.get(
            "appointments",
            []
        )
    ),
)

print(
    "Restrictions:",
    len(
        saved.get(
            "restrictions",
            []
        )
    ),
)

print(
    "Monitoring:",
    len(
        saved.get(
            "monitoring",
            []
        )
    ),
)

print(
    "Warning signs:",
    len(
        saved.get(
            "warning_signs",
            []
        )
    ),
)
