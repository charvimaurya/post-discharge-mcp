"""Process the sample PDF into a recovery state and print it, without database or vector writes."""

from pathlib import Path

from app.ingestion.pipeline import process_document


document_path = Path(__file__).parent / "test_data" / "doc_001.pdf"
recovery_plan = process_document(
    file_bytes=document_path.read_bytes(),
    filename=document_path.name,
    patient_id="demo_patient_001",
    document_id="doc_001"
)

if recovery_plan:
    print("\nRecovery plan successfully processed.")
    print(recovery_plan)
