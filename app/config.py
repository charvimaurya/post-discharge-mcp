"""Shared settings loaded from the project's environment file."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)

REGION = os.environ["AWS_REGION"]
MODEL_MODE = os.getenv("MODEL_MODE", "test")
TEST_MODEL_ID = os.getenv("TEST_MODEL_ID", "")
FINAL_EXTRACTION_MODEL_ID = os.getenv("FINAL_EXTRACTION_MODEL_ID", "")
FINAL_AGENT_MODEL_ID = os.getenv("FINAL_AGENT_MODEL_ID", "")
PROCESSING_QUEUE_URL = os.getenv(
    "PROCESSING_QUEUE_URL",
    os.getenv("SQS_DOCUMENT_QUEUE_URL", ""),
)
DOCUMENT_QUEUE_URL = PROCESSING_QUEUE_URL
DOCUMENT_BUCKET = os.getenv(
    "DOCUMENT_BUCKET",
    os.getenv("AFTERWARD_BUCKET", os.getenv("CARELOOP_BUCKET", "")),
)
RECOVERY_STATE_TABLE = os.environ.get(
    "RECOVERY_STATE_TABLE",
    "PostDischargeRecoveryState",
)
EVENT_HISTORY_TABLE = os.environ.get(
    "EVENT_HISTORY_TABLE",
    "PostDischargeEventHistory",
)
IMAGE_MODEL_ID = os.environ.get("IMAGE_MODEL_ID", "")  # Bedrock Nova model for image/handwriting
EXTRACTION_MODEL_ID = os.environ.get("BEDROCK_EXTRACTION_MODEL_ID", "")
AGENT_MODEL_ID = os.environ.get("AGENT_MODEL_ID", "")
# ---------------------------------------------------------
# S3 VECTORS / RAG
# ---------------------------------------------------------
S3_VECTOR_BUCKET = os.getenv(
    "S3_VECTOR_BUCKET",
    "careloop-vectors-992617582533-london",
)
S3_VECTOR_INDEX = os.getenv(
    "S3_VECTOR_INDEX",
    "careloop-discharge-index",
)
EMBEDDING_MODEL_ID = os.getenv(
    "EMBEDDING_MODEL_ID",
    "amazon.titan-embed-text-v2:0",
)
EMBEDDING_DIMENSIONS = int(os.getenv("EMBEDDING_DIMENSIONS", "512"))
# ---------------------------------------------------------
# MCP HTTP AUTH
# ---------------------------------------------------------
# Local development: MCP_AUTH_TOKEN. Deployment: MCP_AUTH_TOKEN_SECRET_ARN
# (the token is read from Secrets Manager, never stored in code).
MCP_AUTH_TOKEN = os.getenv("MCP_AUTH_TOKEN", "")
MCP_AUTH_TOKEN_SECRET_ARN = os.getenv("MCP_AUTH_TOKEN_SECRET_ARN", "")
MCP_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "MCP_ALLOWED_ORIGINS",
        "http://localhost:3000,"
        "http://127.0.0.1:3000",
    ).split(",")
    if origin.strip()
]


def _select_model_id(final_setting: str, final_model_id: str) -> str:
    if MODEL_MODE == "test":
        setting, model_id = "TEST_MODEL_ID", TEST_MODEL_ID
    elif MODEL_MODE == "final":
        setting, model_id = final_setting, final_model_id
    else:
        raise ValueError(f"Unsupported MODEL_MODE: {MODEL_MODE}")
    if not model_id or not model_id.strip():
        raise ValueError(f"{setting} must be set for MODEL_MODE={MODEL_MODE}")
    return model_id


def get_extraction_model_id() -> str:
    """Select the development model or final-quality extraction model."""
    return _select_model_id("FINAL_EXTRACTION_MODEL_ID", FINAL_EXTRACTION_MODEL_ID)


def get_agent_model_id() -> str:
    """Select the development model or final-quality agent model."""
    return _select_model_id("FINAL_AGENT_MODEL_ID", FINAL_AGENT_MODEL_ID)
