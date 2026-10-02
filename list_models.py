import boto3
b = boto3.client("bedrock", region_name="eu-west-2")
for m in b.list_foundation_models()["modelSummaries"]:
    mid = m["modelId"]
    if "claude" in mid.lower() or "titan-embed" in mid.lower():
        print(mid)