from app.ingestion.pdf_processor import extract_text

pages = extract_text("test_data/discharge.pdf")

for page in pages:
    print(f"\n===== PAGE {page['page']} =====\n")
    print(page["text"])
