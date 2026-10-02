from pathlib import Path, PurePosixPath
import mimetypes
import boto3
from app import config

if not config.DOCUMENT_BUCKET:
    raise RuntimeError(
        "DOCUMENT_BUCKET (or CARELOOP_BUCKET) environment variable is not set."
    )

s3 = boto3.client(
    "s3",
    region_name=config.REGION
)

ALLOWED_EXTENSIONS = {
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
}

def upload_document(
    file_path: str,
    patient_id: str,
    document_id: str,
) -> dict:

    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(
            f"File not found: {file_path}"
        )

    extension = path.suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type: {extension}"
        )

    key = (
        f"patients/{patient_id}/"
        f"documents/{document_id}"
        f"{extension}"
    )

    content_type, _ = mimetypes.guess_type(
        str(path)
    )

    if content_type is None:
        content_type = "application/octet-stream"

    s3.upload_file(
        Filename=str(path),
        Bucket=config.DOCUMENT_BUCKET,
        Key=key,
        ExtraArgs={
            "ContentType": content_type,
            "ServerSideEncryption": "AES256",
        },
    )

    return {
        "bucket": config.DOCUMENT_BUCKET,
        "key": key,
        "patient_id": patient_id,
        "document_id": document_id,
        "source_type": extension.lstrip("."),
    }

def download_document(
    key: str,
) -> bytes:
    response = s3.get_object(
        Bucket=config.DOCUMENT_BUCKET,
        Key=key,
    )
    return response["Body"].read()

def build_document_key(
    patient_id: str,
    document_id: str,
    extension: str,
) -> str:

    if not extension.startswith("."):
        extension = f".{extension}"

    return (
        f"patients/{patient_id}/"
        f"documents/{document_id}"
        f"{extension.lower()}"
    )


def parse_document_key(key: str) -> dict:
    """
    Take an S3 object key like:

    patients/demo_patient_001/documents/doc_001.pdf

    and extract:

    patient_id = demo_patient_001
    document_id = doc_001
    extension = .pdf
    """

    # Turn the S3 key string into separate path parts.
    #
    # Example:
    #
    # "patients/demo_patient_001/documents/doc_001.pdf"
    #
    # becomes:
    #
    # (
    #     "patients",
    #     "demo_patient_001",
    #     "documents",
    #     "doc_001.pdf"
    # )
    parts = PurePosixPath(key).parts

    # Make sure the S3 key follows the structure
    # that CareLoop expects:
    #
    # patients/{patient_id}/documents/{filename}
    #
    # We expect exactly 4 parts:
    #
    # parts[0] = "patients"
    # parts[1] = patient_id
    # parts[2] = "documents"
    # parts[3] = filename
    #
    # If the key does not match this structure,
    # reject it.
    if (
        len(parts) != 4
        or parts[0] != "patients"
        or parts[2] != "documents"
    ):
        raise ValueError(
            f"Invalid CareLoop document key: {key}"
        )

    # The second part of the key is the patient ID.
    #
    # Example:
    # parts[1] = "demo_patient_001"
    patient_id = parts[1]

    # The fourth part is the actual filename.
    #
    # Example:
    # parts[3] = "doc_001.pdf"
    filename = parts[3]

    # .stem removes the file extension.
    #
    # Example:
    # "doc_001.pdf"
    # becomes:
    # "doc_001"
    document_id = PurePosixPath(filename).stem

    # .suffix gets the file extension.
    #
    # Example:
    # "doc_001.pdf"
    # becomes:
    # ".pdf"
    #
    # .lower() makes sure:
    #
    # ".PDF"
    # becomes:
    # ".pdf"
    extension = PurePosixPath(filename).suffix.lower()

    # Return the useful information
    # as a dictionary.
    return {
        "patient_id": patient_id,
        "document_id": document_id,
        "extension": extension,
    }
