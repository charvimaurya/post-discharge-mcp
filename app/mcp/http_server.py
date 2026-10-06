import os

from mcp.server.transport_security import (
    TransportSecuritySettings,
)

from app import config

from app.mcp.http_auth import (
    MCPAuthenticationMiddleware,
)

from app.mcp.server import mcp


# Base allowed hosts — always permit local dev.
_allowed_hosts = [
    "localhost:*",
    "127.0.0.1:*",
]

# In production the ALB forwards requests whose Host header is the
# ALB DNS name.  Add it so DNS-rebinding protection doesn't reject them.
_alb_host = os.getenv("ALB_HOST", "").strip()
if _alb_host:
    _allowed_hosts.append(_alb_host)

# When CloudFront sits in front of the ALB it forwards the CloudFront
# domain as the Host header.  Add it too.
_https_host = os.getenv("HTTPS_HOST", "").strip()
if _https_host:
    _allowed_hosts.append(_https_host)


transport_security = (
    TransportSecuritySettings(
        enable_dns_rebinding_protection=True,

        allowed_hosts=_allowed_hosts,

        allowed_origins=(
            config.MCP_ALLOWED_ORIGINS
        ),
    )
)


mcp_app = mcp.streamable_http_app(
    streamable_http_path="/mcp",

    # Easier for this hackathon server.
    json_response=True,

    # Required by your implementation plan.
    stateless_http=True,

    transport_security=transport_security,
)


app = MCPAuthenticationMiddleware(
    mcp_app
)