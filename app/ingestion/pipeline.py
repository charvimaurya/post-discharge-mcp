from app.ingestion.bedrock import invoke_extraction_model
from app.ingestion.normalizer import normalize_recovery_plan
from app.ingestion.pdf_processor import extract_text as extract_pdf_text
from app.ingestion.validator import validate_recovery_plan


def process_text(
    text: str,
    patient_id: str,
    document_id: str,
):
    extracted = invoke_extraction_model(text)

    state = normalize_recovery_plan(
        extracted=extracted,
        patient_id=patient_id,
        document_id=document_id,
    )

    state = validate_recovery_plan(state)

    return state


def combine_pages(
    pages: list[dict],
) -> str:
    parts = []
    for page in pages:
        page_number = page["page"]
        text = page["text"]
        parts.append(f"[Page {page_number}]\n{text}")
    return "\n\n".join(parts)


def process_pdf(
    file_bytes: bytes,
    patient_id: str,
    document_id: str,
):
    pages = extract_pdf_text(file_bytes)
    text = combine_pages(pages)
    return process_text(
        text=text,
        patient_id=patient_id,
        document_id=document_id,
    )


def process_image(
    file_bytes: bytes,
    filename: str,
    patient_id: str,
    document_id: str,
):
    from app.ingestion.image_processor import extract_text_from_image

    pages = extract_text_from_image(
        file_bytes=file_bytes,
        filename=filename,
    )
    text = combine_pages(pages)
    return process_text(
        text=text,
        patient_id=patient_id,
        document_id=document_id,
    )


def process_document(
    file_bytes: bytes,
    filename: str,
    patient_id: str,
    document_id: str,
):
    """Process an uploaded document without coupling callers to its processor."""
    extension = Path(filename).suffix.lower()
    if extension == ".pdf":
        return process_pdf(
            file_bytes=file_bytes,
            patient_id=patient_id,
            document_id=document_id,
        )
    if extension in {".jpg", ".jpeg", ".png"}:
        return process_image(
            file_bytes=file_bytes,
            filename=filename,
            patient_id=patient_id,
            document_id=document_id,
        )
    raise ValueError(f"Unsupported document type: {extension}")
from pathlib import Path
