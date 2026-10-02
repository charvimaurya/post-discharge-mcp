from mcp_server.services.s3_service import (
    download_document,
)

from app.ingestion.pdf_processor import (
    extract_text as extract_pdf_text,
)


KEY = (
    "patients/demo_patient_001/"
    "documents/s3_test_doc_001.pdf"
)

file_bytes = download_document(KEY)

pages = extract_pdf_text(
    file_bytes
)

print(
    "Pages:",
    len(pages)
)

for page in pages:
    print(
        "\nPAGE",
        page["page"]
    )

    print(
        page["text"][:500]
    )
