from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pprint import pprint

from app.aws.s3_service import (
    parse_document_key,
)

# This is an example S3 object key.
key = (
    "patients/demo_patient_001/"
    "documents/doc_001.pdf"
)

# Send the key into our parser.
result = parse_document_key(key)

# Print the extracted values nicely.
pprint(result)