from pprint import pprint

from mcp_server.services.s3_service import (
    upload_document,
)


result = upload_document(
    file_path="test_data/discharge.pdf",
    patient_id="demo_patient_001",
    document_id="s3_test_doc_001",
)

pprint(result)