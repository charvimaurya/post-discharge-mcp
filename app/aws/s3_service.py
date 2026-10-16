"""Store and retrieve Afterward discharge documents in Amazon S3.

Documents use the key patients/{patient_id}/documents/{document_id}.{extension}.
S3 keys identify objects within a bucket; they are not local filesystem paths.
This module handles storage only. Extraction and RecoveryState persistence
happen in the ingestion pipeline. S3-to-SQS notifications are configured in AWS,
not sent explicitly by these functions.
"""

from pathlib import Path, PurePosixPath
import mimetypes
import boto3
from app import config

# Read settings through the shared config so local scripts and Lambda use the
# same bucket and region. The bucket is checked when S3 is used, not at import,
# so code and tests that never touch S3 still load without it.
MISSING_BUCKET_MESSAGE = (
    "DOCUMENT_BUCKET (or AFTERWARD_BUCKET) environment variable is not set."
)


def document_bucket() -> str:
    """The configured upload bucket. Raises a clear error naming the setting if it is missing."""

    if not config.DOCUMENT_BUCKET:
        raise RuntimeError(MISSING_BUCKET_MESSAGE)

    return config.DOCUMENT_BUCKET


# Reuse one client across calls. Boto3 obtains credentials from its normal
# credential chain (for example, a local AWS profile or Lambda execution role).
s3 = boto3.client(
    "s3",
    region_name=config.REGION
)

# Upload validation checks the filename extension, not the file's contents.
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
    """Upload a local PDF or image and return its bucket, key, and identifiers.

    Raises FileNotFoundError for a missing path and ValueError for an unsupported
    extension. AWS errors propagate to the caller. Reusing the same patient ID,
    document ID, and extension writes to the same S3 key.
    """

    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(
            f"File not found: {file_path}"
        )

    # Normalize extensions so names such as discharge.PDF are accepted too.
    extension = path.suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type: {extension}"
        )

    # Keep the patient and document identifiers in the key so the worker can
    # recover them from an S3 notification without opening the document.
    key = (
        f"patients/{patient_id}/"
        f"documents/{document_id}"
        f"{extension}"
    )

    # Set S3 metadata from the filename (e.g. application/pdf or image/jpeg).
    # Use a generic binary type if the system cannot identify a MIME type.
    content_type, _ = mimetypes.guess_type(
        str(path)
    )

    if content_type is None:
        content_type = "application/octet-stream"

    # upload_file transfers the local file. AES256 requests S3-managed
    # server-side encryption (SSE-S3) for the stored object.
    bucket = document_bucket()

    s3.upload_file(
        Filename=str(path),
        Bucket=bucket,
        Key=key,
        ExtraArgs={
            "ContentType": content_type,
            "ServerSideEncryption": "AES256",
        },
    )

    # Return metadata for callers to log or pass on; source_type omits the dot.
    return {
        "bucket": bucket,
        "key": key,
        "patient_id": patient_id,
        "document_id": document_id,
        "source_type": extension.lstrip("."),
    }

def download_document(
    key: str,
) -> bytes:
    """Read an object's complete contents from the configured bucket.

    Supply an object key, not an s3:// URL. The bytes can be passed directly to
    the PDF/image pipeline; missing-object and permission errors propagate.
    """
    bucket = document_bucket()
    response = s3.get_object(
        Bucket=bucket,
        Key=key,
    )
    # S3 returns a streaming body. Reading it here loads the whole file in memory.
    return response["Body"].read()

def build_document_key(
    patient_id: str,
    document_id: str,
    extension: str,
) -> str:
    """Build a Afterward key without uploading a file or making an AWS call.

    Accept extensions with or without a leading dot, such as 'PDF' or '.pdf'.
    This helper formats the key; it does not validate supported file types.
    """

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

    # S3 keys use forward slashes regardless of the host operating system,
    # so use PurePosixPath rather than a platform-dependent filesystem path.
    # Callers must URL-decode keys from S3 notifications before passing them here.
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
    # that Afterward expects:
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
            f"Invalid Afterward document key: {key}"
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
