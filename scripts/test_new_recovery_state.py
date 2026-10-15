"""Process the sample PDF into the new RecoveryState and print its serialized fields."""

from pathlib import Path
from dataclasses import asdict
import json
import sys

# Support direct execution from scripts/ without requiring package installation.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.test_letters import DEFAULT_TEST_LETTER
from app.ingestion.pipeline import (
    process_document,
)


PDF_PATH = DEFAULT_TEST_LETTER


file_bytes = Path(
    PDF_PATH
).read_bytes()


state = process_document(
    file_bytes=file_bytes,
    filename=PDF_PATH.name,
    patient_id="demo_patient_001",
    document_id="new_schema_local_001",
)


print(
    json.dumps(
        asdict(state),
        indent=2,
        default=str,
    )
)
