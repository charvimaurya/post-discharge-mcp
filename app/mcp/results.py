
from decimal import Decimal
from typing import Any


def to_json_safe(value: Any) -> Any:
    """
    Convert values returned by AWS/DynamoDB into normal
    JSON-compatible Python values.
    """

    if isinstance(value, Decimal):
        if value % 1 == 0:
            return int(value)

        return float(value)

    if isinstance(value, dict):
        return {
            key: to_json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [
            to_json_safe(item)
            for item in value
        ]

    return value


def success_result(
    *,
    data: Any,
    message: str,
) -> dict:
    """
    Standard successful MCP tool result.
    """

    return {
        "ok": True,
        "data": to_json_safe(data),
        "message": message,
    }


def error_result(
    *,
    code: str,
    message: str,
    next_step: str,
    details: dict | None = None,
) -> dict:
    """
    Standard recoverable MCP tool failure.
    """

    result = {
        "ok": False,
        "error": {
            "code": code,
            "message": message,
            "next_step": next_step,
        },
    }

    if details:
        result["error"]["details"] = to_json_safe(
            details
        )

    return result