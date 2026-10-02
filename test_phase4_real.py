from pathlib import Path

from app.ingestion.pdf_processor import extract_text as extract_pdf_text
from app.ingestion.pipeline import combine_pages, process_text


def main():
    pdf_path = Path(__file__).parent / "test_data" / "discharge.pdf"
    file_bytes = pdf_path.read_bytes()
    pages = extract_pdf_text(file_bytes)
    text = combine_pages(pages)

    state = process_text(
        text=text,
        patient_id="demo_patient_001",
        document_id="test_doc_001",
    )
    print(state)


if __name__ == "__main__":
    main()
