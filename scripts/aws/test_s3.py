from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.aws.s3_service import upload_document


result = upload_document(
    file_path=str(PROJECT_ROOT / "test_data" / "test_image1.jpeg"),
    patient_id="demo_patient_001",
    document_id="handwritten_discharge_001"
)


print(result)