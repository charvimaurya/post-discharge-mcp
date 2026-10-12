"""
What may go into a log line.

Logs reach CloudWatch and the console, so they hold ids, counts, timings
and error TYPES only. Never letter text, medicine names, chat messages or
patient names. Exception messages are not safe: a schema error can quote
extracted letter text, and an AWS error can echo a request.
"""

from botocore.exceptions import ClientError


def safe_error(exc: BaseException) -> str:
    """'ValueError', or 'ClientError(ValidationException)': the type, never the message."""

    name = type(exc).__name__

    if isinstance(exc, ClientError):
        code = exc.response.get("Error", {}).get("Code")
        if code:
            return f"{name}({code})"

    return name
