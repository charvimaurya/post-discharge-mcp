from pprint import pprint

from mcp_server.services.s3_service import (
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