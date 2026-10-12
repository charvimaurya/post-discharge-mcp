"""
Re-read Margaret's SYNTHETIC letter with the CURRENT code, locally.

Runs the same steps as the document Lambda (extract with Bedrock,
normalise, validate, save, index for search) without uploading to S3,
so the deployed Lambda (which may run older extraction code) does not
also process it. demo_patient_001 only.

This replaces her recovery plan in DynamoDB. Afterwards, run:

    python scripts/reset_demo_patient.py --confirm

Usage:

    python scripts/ingestion/reingest_demo_letter.py --confirm
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.clock import system_now_utc
from app.database.recovery_state import save_recovery_state
from app.ingestion.pipeline import process_document_with_pages
from app.rag.service import index_document_pages


# Hard-coded on purpose: never a real patient.
PATIENT_ID = "demo_patient_001"
LETTER = PROJECT_ROOT / "tests" / "fixtures" / "letter1_margaret_knee_replacement_SYNTHETIC.pdf"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--confirm", action="store_true", help="Required. Without it, nothing is changed.")
    args = parser.parse_args()

    if not args.confirm:
        print(f"This replaces {PATIENT_ID}'s recovery plan. Nothing was changed. Re-run with --confirm.")
        sys.exit(1)

    document_id = f"letter1_{system_now_utc():%Y%m%d%H%M%S}"

    state, pages = process_document_with_pages(
        file_bytes=LETTER.read_bytes(),
        filename=LETTER.name,
        patient_id=PATIENT_ID,
        document_id=document_id,
    )

    state.ingestion_status = "indexing"
    save_recovery_state(state)

    vectors = index_document_pages(patient_id=PATIENT_ID, document_id=document_id, pages=pages)

    state.ingestion_status = "ready"
    save_recovery_state(state)

    print(f"Patient:      {PATIENT_ID}")
    print(f"Document:     {document_id}")
    print(f"Medicines:    {len(state.medications)}   Tasks: {len(state.tasks)}   "
          f"Appointments: {len(state.appointments)}   Restrictions: {len(state.restrictions)}")
    print(f"Diet advice:  {len(state.diet_advice)}")
    for advice in state.diet_advice:
        flag = "  (needs confirmation)" if advice.needs_confirmation else ""
        print(f"  [{advice.kind}] {advice.text}{flag}")
    print(f"Search index: {vectors} chunks")
    print("\nNow run: python scripts/reset_demo_patient.py --confirm")


if __name__ == "__main__":
    main()
