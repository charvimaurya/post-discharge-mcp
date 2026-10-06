"""
Request-scoped PatientContext for MCP tools.

HTTP request -> authentication -> PatientContext -> MCP tool.

Authentication sets the context for the current request;
tools read it with get_current_patient_context() and never
accept patient_id from tool arguments.

A ContextVar is used instead of a module-level global so that
concurrent requests cannot overwrite each other's patient.
"""

from contextvars import ContextVar, Token

from app.auth.patient_scope import PatientContext


_current_patient_context: ContextVar[
    PatientContext | None
] = ContextVar(
    "current_patient_context",
    default=None,
)


def set_current_patient_context(
    context: PatientContext,
) -> Token:
    """
    Set PatientContext for the current HTTP request.
    """

    return _current_patient_context.set(
        context
    )


def reset_current_patient_context(
    token: Token,
) -> None:
    """
    Clear/restore request context after the request ends.
    """

    _current_patient_context.reset(
        token
    )


def get_current_patient_context() -> PatientContext:
    """
    Return the authenticated patient's context.

    MCP tools must use this instead of accepting patient_id
    from tool arguments.
    """

    context = _current_patient_context.get()

    if context is None:
        raise RuntimeError(
            "No authenticated PatientContext is available."
        )

    return context


def get_demo_patient_context() -> PatientContext:
    """
    Return the fixed synthetic demo identity (no authentication performed).

    Used by tests and as the identity the demo authentication
    step resolves to. Tools must not call this directly.
    """

    return PatientContext(
        user_id="demo_user_001",
        patient_id="demo_patient_001",
        session_id="demo_session_001",
    )
