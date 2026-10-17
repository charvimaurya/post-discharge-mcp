"""Resolve the MCP HTTP bearer token from local config or AWS Secrets Manager."""

from functools import lru_cache

import boto3

from app import config
from app.auth.bridge_auth import is_production


@lru_cache(maxsize=1)
def get_mcp_auth_token() -> str:
    """
    Return the expected MCP bearer token.

    Local development sets MCP_AUTH_TOKEN directly. Deployments
    set MCP_AUTH_TOKEN_SECRET_ARN and the token is read once from
    Secrets Manager. Local development prefers MCP_AUTH_TOKEN;
    production/ECS requires the secret ARN and ignores a plain token.
    """

    if is_production() and not config.MCP_AUTH_TOKEN_SECRET_ARN.strip():
        raise ValueError("Production MCP credentials require MCP_AUTH_TOKEN_SECRET_ARN")

    if not is_production() and config.MCP_AUTH_TOKEN.strip():
        return config.MCP_AUTH_TOKEN.strip()

    if config.MCP_AUTH_TOKEN_SECRET_ARN.strip():
        client = boto3.client(
            "secretsmanager",
            region_name=config.REGION,
        )
        response = client.get_secret_value(
            SecretId=config.MCP_AUTH_TOKEN_SECRET_ARN.strip()
        )
        token = response.get("SecretString", "").strip()

        if not token:
            raise ValueError(
                "MCP_AUTH_TOKEN_SECRET_ARN secret has no SecretString value"
            )

        return token

    raise ValueError(
        "Set MCP_AUTH_TOKEN for local development or "
        "MCP_AUTH_TOKEN_SECRET_ARN for deployment"
    )
