from dataclasses import asdict

from mcp_server.services.dynamodb_service import recovery_table


def save_recovery_plan(recovery_plan):
    item = asdict(recovery_plan)

    recovery_table.put_item(
        Item=item
    )

    return item