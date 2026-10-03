from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pprint import pprint

from app.database.recovery_state import (
    save_recovery_state,
)

from app.aws.s3_service import (
    download_document,
)

from app.ingestion.pipeline import (
    process_pdf,
)


PATIENT_ID = "demo_patient_001"
DOCUMENT_ID = "s3_test_doc_001"

KEY = (
    f"patients/{PATIENT_ID}/"
    f"documents/{DOCUMENT_ID}.pdf"
)


file_bytes = download_document(
    KEY
)

state = process_pdf(
    file_bytes=file_bytes,
    patient_id=PATIENT_ID,
    document_id=DOCUMENT_ID,
)

save_recovery_state(state)
print("RecoveryState saved")

pprint(state)
