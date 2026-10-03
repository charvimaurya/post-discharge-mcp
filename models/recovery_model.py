"""Define the recovery-state, instruction, and source-evidence dataclasses shared by the application."""

from dataclasses import dataclass, field
from typing import Optional, Any


@dataclass
class Source:
    document_id: str
    page: Optional[int] = None
    snippet: Optional[str] = None
    source_type: str = "document"


@dataclass
class Medication:
    id: str
    name: str
    dose: Optional[str] = None
    frequency: Optional[str] = None
    duration: Optional[str] = None
    notes: Optional[str] = None

    status: str = "pending"
    needs_confirmation: bool = False

    source: Optional[Source] = None


@dataclass
class Task:
    id: str
    description: str
    timing: Optional[str] = None

    status: str = "pending"
    needs_confirmation: bool = False

    source: Optional[Source] = None


@dataclass
class Appointment:
    id: str

    with_: Optional[str] = None
    date: Optional[str] = None
    time: Optional[str] = None
    location: Optional[str] = None

    status: str = "unknown"
    notes: Optional[str] = None

    needs_confirmation: bool = False

    source: Optional[Source] = None


@dataclass
class Monitoring:
    id: str
    what: str
    how_often: Optional[str] = None
    threshold: Optional[str] = None

    needs_confirmation: bool = False
    source: Optional[Source] = None


@dataclass
class RecoveryState:
    patient_id: str
    document_id: str

    discharge_date: Optional[str] = None

    medications: list[Medication] = field(default_factory=list)
    tasks: list[Task] = field(default_factory=list)
    appointments: list[Appointment] = field(default_factory=list)

    restrictions: list[dict[str, Any]] = field(default_factory=list)
    monitoring: list[Monitoring] = field(default_factory=list)
    warning_signs: list[dict[str, Any]] = field(default_factory=list)

    ingestion_status: str = "processing"

    pending_checkin: Optional[dict] = None

    last_updated: Optional[str] = None

    # Patient's local timezone for future reminder scheduling.
    timezone: str = "Europe/London"
