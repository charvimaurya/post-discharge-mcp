from pathlib import Path
import sys

# Direct execution puts this script folder on the import path; include project packages.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.rag.service import (
    index_document_pages,
)


PATIENT_ID = "demo_patient_001"

DOCUMENT_ID = "rag_test_001"


pages = [
    {
        "page": 1,
        "text": """
        Activity instructions:
        Take short walks daily as tolerated and gradually
        increase your activity.

        Driving:
        Do not drive for at least 7 days and until reviewed
        by your GP.

        Avoid heavy lifting over 5 kg for 2 weeks.
        """,
    },
    {
        "page": 2,
        "text": """
        Call 999 immediately if you experience severe or
        worsening breathlessness, chest pain, confusion,
        or blue lips or fingertips.
        """,
    },
]


count = index_document_pages(
    patient_id=PATIENT_ID,
    document_id=DOCUMENT_ID,
    pages=pages,
)

print(
    f"Indexed {count} chunks"
)
