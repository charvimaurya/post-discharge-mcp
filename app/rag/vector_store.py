"""
Low-level Amazon S3 Vectors access.

Higher-level AfterWard retrieval logic should live in
service.py, not here.
"""

import boto3

from app import config


s3vectors = boto3.client(
    "s3vectors",
    region_name=config.REGION,
)


MISSING_VECTOR_BUCKET_MESSAGE = "S3_VECTOR_BUCKET is not set. Add it to the root .env."


def _vector_bucket() -> str:
    """The configured vector bucket. Raises a clear error naming the setting if it is missing."""

    if not config.S3_VECTOR_BUCKET:
        raise RuntimeError(MISSING_VECTOR_BUCKET_MESSAGE)

    return config.S3_VECTOR_BUCKET


def put_chunks(
    *,
    patient_id: str,
    document_id: str,
    chunks: list[dict],
    embeddings: list[list[float]],
) -> None:
    """
    Write document chunks and their embeddings into the
    AfterWard S3 Vectors index.
    """

    if len(chunks) != len(
        embeddings
    ):
        raise ValueError(
            "chunks and embeddings must "
            "have the same length"
        )

    vectors = []

    for chunk, embedding in zip(
        chunks,
        embeddings,
    ):

        if (
            len(embedding)
            != config.EMBEDDING_DIMENSIONS
        ):
            raise ValueError(
                "Embedding has incorrect "
                "dimension"
            )

        vectors.append(
            {
                # Unique key in this index.
                "key":
                    chunk["chunk_id"],

                "data": {
                    "float32": [
                        float(value)
                        for value
                        in embedding
                    ]
                },

                "metadata": {
                    # FILTERABLE
                    "patient_id":
                        patient_id,

                    # FILTERABLE
                    "document_id":
                        document_id,

                    # Page is useful provenance.
                    "page":
                        chunk["page"],

                    # NON-FILTERABLE
                    "section":
                        chunk.get(
                            "section",
                            "",
                        ),

                    # NON-FILTERABLE
                    # Original source material returned
                    # with a retrieval result.
                    "text":
                        chunk["text"],
                },
            }
        )

    if not vectors:
        return

    bucket = _vector_bucket()

    s3vectors.put_vectors(
        vectorBucketName=
            bucket,

        indexName=
            config.S3_VECTOR_INDEX,

        vectors=
            vectors,
    )


def query_chunks(
    *,
    query_embedding: list[float],
    patient_id: str,
    document_id: str,
    top_k: int = 5,
) -> list[dict]:
    """
    Search discharge vectors belonging ONLY to the
    authenticated patient's current document.

    Both patient_id and document_id are enforced inside
    the S3 Vectors query.

    This prevents:
    - another patient's chunks being returned
    - old documents for the same demo patient being returned
    """

    if (
        len(query_embedding)
        != config.EMBEDDING_DIMENSIONS
    ):

        raise ValueError(
            "Query embedding dimension "
            "does not match index"
        )


    bucket = _vector_bucket()

    response = (
        s3vectors.query_vectors(
            vectorBucketName=
                bucket,

            indexName=
                config.S3_VECTOR_INDEX,

            queryVector={
                "float32": [
                    float(value)
                    for value
                    in query_embedding
                ]
            },

            topK=
                top_k,

            # SECURITY:
            # Search only the authenticated patient's
            # CURRENT discharge document.
            filter={
                "$and": [
                    {
                        "patient_id": {
                            "$eq": patient_id
                        }
                    },
                    {
                        "document_id": {
                            "$eq": document_id
                        }
                    },
                ]
            },

            returnMetadata=
                True,

            returnDistance=
                True,
        )
    )


    return response.get(
        "vectors",
        [],
    )