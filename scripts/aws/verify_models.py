"""Invoke configured extraction, agent, and embedding models to check live Bedrock access."""

import json, boto3
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import config

br = boto3.client("bedrock-runtime", region_name=config.REGION)

for label, mid in [("extraction", config.get_extraction_model_id()), ("agent", config.get_agent_model_id())]:
    r = br.converse(
        modelId=mid,
        messages=[{"role": "user", "content": [{"text": "Reply with OK"}]}],
        inferenceConfig={"maxTokens": 10, "temperature": 0},
    )
    print(label, "->", r["output"]["message"]["content"][0]["text"])

r = br.invoke_model(
    modelId=config.EMBEDDING_MODEL_ID,
    body=json.dumps({"inputText": "hello", "dimensions": 512}),
)
vec = json.loads(r["body"].read())["embedding"]
print("embedding length:", len(vec))   # expect 512
