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

    s3vectors.put_vectors(
        vectorBucketName=
            config.S3_VECTOR_BUCKET,

        indexName=
            config.S3_VECTOR_INDEX,

        vectors=
            vectors,
    )


def query_chunks(
    *,
    query_embedding: list[float],
    patient_id: str,
    top_k: int = 5,
) -> list[dict]:
    """
    Search the vector index.

    SECURITY REQUIREMENT:

    Every query MUST be restricted by patient_id.
    """

    if (
        len(query_embedding)
        != config.EMBEDDING_DIMENSIONS
    ):

        raise ValueError(
            "Query embedding dimension "
            "does not match index"
        )


    response = (
        s3vectors.query_vectors(
            vectorBucketName=
                config.S3_VECTOR_BUCKET,

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

            filter={
                "patient_id":
                    patient_id
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