from mcp_server.services.s3_service import (
    download_document,
)


KEY = (
    "patients/demo_patient_001/"
    "documents/s3_test_doc_001.pdf"
)

file_bytes = download_document(KEY)

print(
    "Downloaded bytes:",
    len(file_bytes),
)