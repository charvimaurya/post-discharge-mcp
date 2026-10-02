import boto3
from app import config

print("identity:", boto3.client("sts").get_caller_identity()["Account"])
boto3.client("bedrock-runtime", region_name=config.REGION)
boto3.client("dynamodb", region_name=config.REGION)
print("clients created in", config.REGION)