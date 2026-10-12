import hmac

from starlette.responses import JSONResponse

from app.auth.mcp_auth import (
    get_expected_mcp_token,
)

from app.auth.patient_scope import (
    PatientContext,
)

from app.mcp.context import (
    reset_current_patient_context,
    set_current_patient_context,
)

from app.observability.log import (
    reset_request_id,
    set_request_id,
)


class MCPAuthenticationMiddleware:
    """
    Protect /mcp with bearer authentication.

    For the hackathon demo, a valid MCP token resolves
    to the synthetic demo patient.

    Production would replace this with account linking /
    Cognito-derived patient identity.
    """

    def __init__(
        self,
        app,
    ):
        self.app = app


    async def __call__(
        self,
        scope,
        receive,
        send,
    ):
        # Non-HTTP traffic is passed through.
        if scope["type"] != "http":
            await self.app(
                scope,
                receive,
                send,
            )
            return

        path = scope.get(
            "path",
            "",
        )

        # /health must remain public.
        if path == "/health":
            await self.app(
                scope,
                receive,
                send,
            )
            return

        # Only protect MCP traffic.
        if path != "/mcp":
            await self.app(
                scope,
                receive,
                send,
            )
            return

        headers = {
            key.decode(
                "latin-1"
            ).lower():
            value.decode(
                "latin-1"
            )
            for key, value
            in scope.get(
                "headers",
                []
            )
        }

        auth_header = headers.get(
            "authorization",
            "",
        )

        if not auth_header.startswith(
            "Bearer "
        ):
            response = JSONResponse(
                {
                    "error": "unauthorized",
                    "message": (
                        "A bearer token is required."
                    ),
                },
                status_code=401,
            )

            await response(
                scope,
                receive,
                send,
            )

            return

        supplied_token = auth_header[
            len("Bearer "):
        ].strip()

        expected_token = (
            get_expected_mcp_token()
        )

        if not hmac.compare_digest(
            supplied_token,
            expected_token,
        ):
            response = JSONResponse(
                {
                    "error": "unauthorized",
                    "message": (
                        "The bearer token is invalid."
                    ),
                },
                status_code=401,
            )

            await response(
                scope,
                receive,
                send,
            )

            return

        # Hackathon authentication mapping.
        #
        # Valid demo token -> demo_patient_001.
        #
        # Crucially, patient_id is derived server-side,
        # never from MCP tool arguments.
        patient_context = PatientContext(
            user_id="demo_user_001",
            patient_id="demo_patient_001",
            session_id="mcp_demo_session",
        )

        context_token = (
            set_current_patient_context(
                patient_context
            )
        )

        # The caller's request id (the bridge sends the one it logged),
        # so each tool's log line can be matched to the chat turn.
        request_token = set_request_id(
            headers.get("x-request-id")
        )

        try:

            await self.app(
                scope,
                receive,
                send,
            )

        finally:

            reset_current_patient_context(
                context_token
            )

            reset_request_id(
                request_token
            )
