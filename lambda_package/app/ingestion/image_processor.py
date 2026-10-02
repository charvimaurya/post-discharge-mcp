from pathlib import Path
import boto3
from app import config

bedrock = boto3.client(
    "bedrock-runtime",
    region_name=config.REGION
)


def extract_text_from_image(
    image_path: str | None = None,
    *,
    file_bytes: bytes | None = None,
    filename: str | None = None,
) -> list[dict]:
    """Transcribe an image from a file path or bytes with a filename."""
    if file_bytes is not None:
        if image_path is not None:
            raise ValueError("Provide either image_path or file_bytes, not both")
        if not filename:
            raise ValueError("filename is required when providing file_bytes")
        path = Path(filename)
        image_bytes = file_bytes
    else:
        if image_path is None:
            raise ValueError("Provide image_path or file_bytes with filename")
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")
        image_bytes = path.read_bytes()
    media_type = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
    }.get(path.suffix.lower(), "image/jpeg")
    image_format = media_type.split("/", 1)[1]

    response = bedrock.converse(
        modelId=config.IMAGE_MODEL_ID,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "text": """
Read this discharge paperwork carefully.

Transcribe all visible text from this image, including handwriting.

Preserve:
- medication names
- doses
- frequencies
- dates
- appointment information
- restrictions
- warning signs
- handwritten instructions

Do not invent or infer missing text.

For any character, digit, or word you are not fully confident about,
wrap it in [?...?] to mark it uncertain — especially digits in doses,
phone numbers, temperatures, and dates, where a misread is dangerous.
If a section is completely illegible, write [unreadable].
Do not guess silently. It is better to mark uncertainty than to
transcribe a confident but possibly wrong value.

Return only the transcription.
"""
                    },
                    {
                        "image": {
                            "format": image_format,
                            "source": {
                                "bytes": image_bytes
                            }
                        }
                    }
                ]
            }
        ],
        inferenceConfig={
            "maxTokens": 4000
        }
    )

    content = response["output"]["message"]["content"]

    text = "\n".join(
        item["text"]
        for item in content
        if "text" in item
    )

    # Return the same structure as the PDF processor
    return [
        {
            "page": 1,
            "text": text
        }
    ]
