"""Upload and download a test image, then process it with Bedrock and print the recovery state."""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pprint import pprint

from app.aws.s3_service import (
    upload_document,
    download_document,
)
from app.ingestion.pipeline import process_image


def main():
    result = upload_document(
        file_path=str(PROJECT_ROOT / "test_data" / "test_image1.jpeg"),
        patient_id="demo_patient_001",
        document_id="s3_image_test_001",
    )

    print("Uploaded to:", result["key"])

    file_bytes = download_document(result["key"])
    print("Downloaded bytes:", len(file_bytes))

    state = process_image(
        file_bytes=file_bytes,
        filename="s3_image_test_001.jpeg",
        patient_id="demo_patient_001",
        document_id="s3_image_test_001",
    )

    pprint(state)
    assert state.ingestion_status == "ready"
    print("OK — S3 image processing completed")


if __name__ == "__main__":
    main()
