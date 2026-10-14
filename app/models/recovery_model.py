"""Define the recovery-state, instruction, and source-evidence dataclasses shared by the application."""

from dataclasses import dataclass, field
from typing import Optional


# These instruction dataclasses have the same fields, defaults and constructor
# order as AfterWard's original types. Keep the application-owned state below.
from discharge_letter_check.models import (
    Appointment, DietAdvice, FollowOn, Medication, Monitoring,
    Restriction, Source, Task, WarningSign,
)


@dataclass
class RecoveryState:
    patient_id: str
    document_id: str

    discharge_date: Optional[str] = None

    # From the letter's "Patient:" line (app/ingestion/patient_name.py). Only the
    # first name is kept; None means AfterWard greets without a name.
    first_name: Optional[str] = None

    medications: list[Medication] = field(default_factory=list)
    tasks: list[Task] = field(default_factory=list)
    appointments: list[Appointment] = field(default_factory=list)

    restrictions: list[Restriction] = field(default_factory=list)
    monitoring: list[Monitoring] = field(default_factory=list)
    warning_signs: list[WarningSign] = field(default_factory=list)
    diet_advice: list[DietAdvice] = field(default_factory=list)

    ingestion_status: str = "processing"

    pending_checkin: Optional[dict] = None

    last_updated: Optional[str] = None

    # Patient's local timezone for future reminder scheduling.
    timezone: str = "Europe/London"
