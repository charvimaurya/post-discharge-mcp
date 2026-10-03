from pathlib import Path
import sys

# Direct execution puts this script folder on the import path; include project packages.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.rag.service import (
    index_document_pages,
    search_discharge_instructions,
)


# ---------------------------------------------------------
# CREATE SECOND PATIENT VECTOR
# ---------------------------------------------------------

index_document_pages(
    patient_id="demo_patient_002",

    document_id="patient2_doc",

    pages=[
        {
            "page": 1,

            "text": (
                "Patient should avoid swimming "
                "for six weeks."
            ),
        }
    ],
)


# ---------------------------------------------------------
# SEARCH AS PATIENT 1
# ---------------------------------------------------------

results = (
    search_discharge_instructions(
        query=(
            "What does my paperwork "
            "say about swimming?"
        ),

        patient_id=
            "demo_patient_001",

        top_k=10,
    )
)


for result in results:

    assert (
        result["document_id"]
        != "patient2_doc"
    )


print(
    "✅ Patient isolation test passed"
)
