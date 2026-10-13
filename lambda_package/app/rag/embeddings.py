"""
Amazon Titan Text Embeddings V2 integration.

AfterWard uses 512-dimensional normalized embeddings.
"""

import json

import boto3

from app import config


bedrock = boto3.client(
    "bedrock-runtime",
    region_name=config.REGION,
)


def embed_text(
    text: str,
) -> list[float]:
    """
    Convert text into a 512-dimensional Titan embedding.
    """

    text = text.strip()

    if not text:
        raise ValueError(
            "Cannot embed empty text"
        )

    request_body = {
        "inputText": text,

        # Must match our S3 Vector index.
        "dimensions":
            config.EMBEDDING_DIMENSIONS,

        # Useful with cosine search.
        "normalize": True,

        "embeddingTypes": [
            "float"
        ],
    }

    response = bedrock.invoke_model(
        modelId=
            config.EMBEDDING_MODEL_ID,

        body=json.dumps(
            request_body
        ),

        contentType=
            "application/json",

        accept=
            "application/json",
    )

    response_body = json.loads(
        response["body"].read()
    )

    embedding = response_body[
        "embedding"
    ]

    if (
        len(embedding)
        != config.EMBEDDING_DIMENSIONS
    ):
        raise ValueError(
            "Unexpected embedding dimension: "
            f"{len(embedding)}"
        )

    # Explicit Python floats are suitable for the SDK.
    return [
        float(value)
        for value in embedding
    ]