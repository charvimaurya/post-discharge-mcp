from mcp_server.services.s3_service import upload_document


result = upload_document(
    file_path="test_data/test_image1.jpeg",
    patient_id="demo_patient_001",
    document_id="handwritten_discharge_001"
)


print(result)