"""Send a short prompt to the hardcoded Nova model and print its live Bedrock response."""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import boto3

bedrock = boto3.client(
    "bedrock-runtime",
    region_name="eu-west-2"
)

MODEL_ID = "global.amazon.nova-2-lite-v1:0"

def main():
    response = bedrock.converse(
        modelId=MODEL_ID,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "text": "Explain what a hospital discharge summary is in one sentence."
                    }
                ]
            }
        ],
        inferenceConfig={
            "maxTokens": 200,
            "temperature": 0
        }
    )

    response_text = response["output"]["message"]["content"][0]["text"]

    print("\n===== BEDROCK RESPONSE =====\n")
    print(response_text)


if __name__ == "__main__":
    main()