"""Search the live vector index for driving evidence and print source details and distances."""

from pathlib import Path
import sys

# Direct execution puts this script folder on the import path; include project packages.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.rag.service import (
    search_discharge_instructions,
)


results = (
    search_discharge_instructions(
        query=(
            "What did my paperwork "
            "say about driving?"
        ),

        patient_id=
            "demo_patient_001",

        top_k=3,
    )
)


print()
print(
    "RAG RESULTS"
)
print(
    "=" * 60
)


for index, result in enumerate(
    results,
    start=1,
):

    print()
    print(
        f"RESULT {index}"
    )

    print(
        "Distance:",
        result["distance"],
    )

    print(
        "Page:",
        result["page"],
    )

    print(
        "Document:",
        result["document_id"],
    )

    print(
        "Text:"
    )

    print(
        result["text"]
    )
