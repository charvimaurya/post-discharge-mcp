"""Carry application-resolved patient identity into service and MCP operations."""

from dataclasses import dataclass


@dataclass(frozen=True)
class PatientContext:
    """Identity supplied by trusted application code, not by a model tool argument.

    This container does not authenticate a user. Local MCP tests use the fixed
    synthetic identity; HTTP authentication must resolve it before production use.
    """

    user_id: str
    patient_id: str
    session_id: str
