import boto3

from app import config


_cached_token: str | None = None


def get_expected_mcp_token() -> str:
    """
    Return the expected MCP bearer token.

    Local development:
        MCP_AUTH_TOKEN

    Deployment:
        AWS Secrets Manager via MCP_AUTH_TOKEN_SECRET_ARN
    """

    global _cached_token

    if _cached_token:
        return _cached_token

    # Local development first.
    if config.MCP_AUTH_TOKEN:
        _cached_token = config.MCP_AUTH_TOKEN
        return _cached_token

    if not config.MCP_AUTH_TOKEN_SECRET_ARN:
        raise RuntimeError(
            "No MCP authentication token configured."
        )

    client = boto3.client(
        "secretsmanager",
        region_name=config.REGION,
    )

    response = client.get_secret_value(
        SecretId=config.MCP_AUTH_TOKEN_SECRET_ARN
    )

    secret = response.get(
        "SecretString"
    )

    if not secret:
        raise RuntimeError(
            "MCP bearer token secret is empty."
        )

    _cached_token = secret

    return _cached_token