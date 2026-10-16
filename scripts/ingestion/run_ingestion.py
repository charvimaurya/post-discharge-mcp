"""Process the sample PDF into a recovery state and print it, without database or vector writes."""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.ingestion.pipeline import process_document
from scripts.test_letters import DEFAULT_TEST_LETTER


document_path = DEFAULT_TEST_LETTER
recovery_plan = process_document(
    file_bytes=document_path.read_bytes(),
    filename=document_path.name,
    patient_id="demo_patient_001",
    document_id="doc_001"
)

if recovery_plan:
    print("\nRecovery plan successfully processed.")
    print(recovery_plan)
