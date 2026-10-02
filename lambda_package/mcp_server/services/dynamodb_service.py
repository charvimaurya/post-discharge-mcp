import boto3
from app import config


dynamodb = boto3.resource(
    "dynamodb",
    region_name=config.REGION
)

recovery_table = dynamodb.Table(
    config.RECOVERY_STATE_TABLE
)

event_table = dynamodb.Table(
    config.EVENT_HISTORY_TABLE
)
