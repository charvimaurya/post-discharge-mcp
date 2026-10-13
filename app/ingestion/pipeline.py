"""Route PDFs and images through extraction, normalization, and validation without saving results."""

from pathlib import Path

from app.ingestion.document_validation import validate_discharge_document
from app.ingestion.patient_name import read_first_name
from app.observability.log import Timer, service_log

from app.ingestion.bedrock import (
    invoke_extraction_model,
)

from app.ingestion.normalizer import (
    normalize_recovery_plan,
)

from app.ingestion.pdf_processor import (
    extract_text as extract_pdf_text,
)

from app.ingestion.validator import (
    validate_recovery_plan,
)


log = service_log("document_lambda")


def process_text(
    text: str,
    patient_id: str,
    document_id: str,
):
    """
    Convert document text into the structured
    RecoveryState used by AfterWard.

    Flow:

    document text
        ↓
    Bedrock structured extraction
        ↓
    normalization
        ↓
    validation
        ↓
    RecoveryState
    """

    validate_discharge_document(text)

    timer = Timer()

    extracted = invoke_extraction_model(
        text
    )

    log("ingest_stage", stage="extracted", document_id=document_id, ms=timer.ms)

    state = normalize_recovery_plan(
        extracted=extracted,
        patient_id=patient_id,
        document_id=document_id,
    )

    # The letter text lets validation keep only word-for-word diet lines.
    state = validate_recovery_plan(
        state,
        document_text=text,
    )

    # The patient's first name, from the letter's own "Patient:" line. Never guessed.
    state.first_name = read_first_name(text)

    log("ingest_stage", stage="checked", document_id=document_id, ms=timer.ms)

    return state


def combine_pages(
    pages: list[dict],
) -> str:
    """
    Combine page-aware extracted text into one string
    for the Bedrock structured extraction model.

    Page markers are deliberately preserved because they
    help Bedrock return page-level source evidence.
    """

    parts = []

    for page in pages:

        page_number = page["page"]
        text = page["text"]

        parts.append(
            f"[Page {page_number}]\n{text}"
        )

    return "\n\n".join(
        parts
    )


def extract_document_pages(
    file_bytes: bytes,
    filename: str,
) -> list[dict]:
    """
    Extract page-aware text from any supported document.

    This function performs only document extraction.

    It does NOT call Bedrock and does NOT create a
    RecoveryState.

    Output:

        [
            {
                "page": 1,
                "text": "..."
            },
            {
                "page": 2,
                "text": "..."
            }
        ]
    """

    extension = (
        Path(filename)
        .suffix
        .lower()
    )

    # -----------------------------------------------------
    # PDF
    # -----------------------------------------------------

    if extension == ".pdf":

        return extract_pdf_text(
            file_bytes
        )


    # -----------------------------------------------------
    # IMAGE
    # -----------------------------------------------------

    if extension in {
        ".jpg",
        ".jpeg",
        ".png",
    }:

        from app.ingestion.image_processor import (
            extract_text_from_image,
        )

        return extract_text_from_image(
            file_bytes=file_bytes,
            filename=filename,
        )


    # -----------------------------------------------------
    # UNSUPPORTED
    # -----------------------------------------------------

    raise ValueError(
        f"Unsupported document type: "
        f"{extension}"
    )


def process_document_with_pages(
    file_bytes: bytes,
    filename: str,
    patient_id: str,
    document_id: str,
):
    """
    Process a document while ALSO preserving the
    page-aware text needed by RAG.

    Returns:

        state, pages

    where:

        state
            = validated RecoveryState for DynamoDB

        pages
            = original page-aware document text
              for S3 Vectors indexing
    """

    # -----------------------------------------------------
    # 1. EXTRACT ORIGINAL PAGE TEXT
    # -----------------------------------------------------

    pages = extract_document_pages(
        file_bytes=file_bytes,
        filename=filename,
    )


    # -----------------------------------------------------
    # 2. COMBINE PAGES FOR STRUCTURED EXTRACTION
    # -----------------------------------------------------

    text = combine_pages(
        pages
    )


    # -----------------------------------------------------
    # 3. CREATE RECOVERYSTATE
    # -----------------------------------------------------

    state = process_text(
        text=text,
        patient_id=patient_id,
        document_id=document_id,
    )


    # -----------------------------------------------------
    # 4. RETURN BOTH OUTPUTS
    # -----------------------------------------------------

    return state, pages


def process_pdf(
    file_bytes: bytes,
    patient_id: str,
    document_id: str,
):
    """
    Existing PDF API.

    Kept so existing tests/callers continue to work.
    """

    filename = (
        f"{document_id}.pdf"
    )

    state, _pages = (
        process_document_with_pages(
            file_bytes=file_bytes,
            filename=filename,
            patient_id=patient_id,
            document_id=document_id,
        )
    )

    return state


def process_image(
    file_bytes: bytes,
    filename: str,
    patient_id: str,
    document_id: str,
):
    """
    Existing image API.

    Kept so existing tests/callers continue to work.
    """

    state, _pages = (
        process_document_with_pages(
            file_bytes=file_bytes,
            filename=filename,
            patient_id=patient_id,
            document_id=document_id,
        )
    )

    return state


def process_document(
    file_bytes: bytes,
    filename: str,
    patient_id: str,
    document_id: str,
):
    """
    Existing public API.

    IMPORTANT:

    This still returns ONLY RecoveryState so none of the
    existing AfterWard code has to change.

    RAG-aware callers should instead use:

        process_document_with_pages()
    """

    state, _pages = (
        process_document_with_pages(
            file_bytes=file_bytes,
            filename=filename,
            patient_id=patient_id,
            document_id=document_id,
        )
    )

    return state