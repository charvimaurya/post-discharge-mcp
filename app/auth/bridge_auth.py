"""Service-to-service bridge authentication. Never log credential headers."""

import hmac
import os

from starlette.responses import JSONResponse


def is_cloud_runtime() -> bool:
    return bool(
        os.getenv("ECS_CONTAINER_METADATA_URI_V4")
        or os.getenv("ECS_CONTAINER_METADATA_URI")
        or os.getenv("AWS_EXECUTION_ENV", "").startswith("AWS_ECS")
    )


def is_production() -> bool:
    return is_cloud_runtime() or os.getenv("CLOCK_MODE", "").strip().lower() == "production"


class BridgeAuthenticationMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if scope.get("path") == "/bridge/health" and scope.get("method") in {"GET", "HEAD"}:
            await self.app(scope, receive, send)
            return
        # Amazon calls /alexa and cannot send the bridge key. The route checks Amazon's request
        # signature, the timestamp and ALEXA_SKILL_ID itself (app.alexa.skill), and refuses otherwise.
        if scope.get("path") == "/alexa" and scope.get("method") == "POST":
            await self.app(scope, receive, send)
            return

        expected = os.getenv("BRIDGE_KEY", "").strip()
        # Missing credentials fail closed in every mode. Cloud keys must have
        # at least 32 characters; health remains available for ALB diagnostics.
        if not expected or (is_production() and len(expected) < 32):
            response = JSONResponse({"error": "Bridge authentication is not configured."}, status_code=503)
        else:
            supplied = [v for k, v in scope.get("headers", []) if k.lower() == b"x-bridge-key"]
            valid = len(supplied) == 1 and hmac.compare_digest(supplied[0], expected.encode("utf-8"))
            if valid:
                await self.app(scope, receive, send)
                return
            response = JSONResponse({"error": "Unauthorized."}, status_code=401)
        await response(scope, receive, send)
