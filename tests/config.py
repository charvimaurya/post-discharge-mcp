import os
from dotenv import load_dotenv
load_dotenv()

REGION = os.environ["AWS_REGION"]
EXTRACTION_MODEL_ID = os.environ.get("BEDROCK_EXTRACTION_MODEL_ID", "")
AGENT_MODEL_ID = os.environ.get("AGENT_MODEL_ID", "")
EMBEDDING_MODEL_ID = os.environ["EMBEDDING_MODEL_ID"]
EMBEDDING_DIMENSIONS = int(os.environ["EMBEDDING_DIMENSIONS"])
# URL of the SQS queue that receives new-document events from S3.
DOCUMENT_QUEUE_URL = os.getenv(
    "SQS_DOCUMENT_QUEUE_URL",
    "",
)