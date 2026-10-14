"""Define the recovery-state, instruction, and source-evidence dataclasses the checker works on."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Source:
    document_id: str
    snippet: str
    page: Optional[int] = None
    read_from_image: bool = False


@dataclass
class Medication:
    id: str
    name: str
    strength: Optional[str] = None
    form: Optional[str] = None
    dose: Optional[str] = None
    site: Optional[str] = None
    times_per_day: Optional[int] = None
    time_of_day: list[str] = field(default_factory=list)
    as_needed: bool = False
    as_needed_reason: Optional[str] = None
    max_per_day: Optional[int] = None
    instructions: Optional[str] = None
    duration_text: Optional[str] = None

    status: str = "pending"
    needs_confirmation: bool = False

    source: Optional[Source] = None


@dataclass
class FollowOn:
    """Do this task for duration_minutes straight after another task (from the letter)."""

    after_task_id: str
    duration_minutes: Optional[int] = None
    source: Optional[Source] = None


@dataclass
class Task:
    id: str
    description: str
    kind: str = "other"
    times_per_day: Optional[int] = None
    time_of_day: list[str] = field(default_factory=list)
    clock_times: list[str] = field(default_factory=list)
    details: Optional[str] = None
    duration_text: Optional[str] = None

    status: str = "pending"
    needs_confirmation: bool = False

    source: Optional[Source] = None

    follow_on: Optional[FollowOn] = None


@dataclass
class Appointment:
    id: str
    title: str
    date: Optional[str] = None
    time: Optional[str] = None
    location: Optional[str] = None
    conflicting_dates: list[str] = field(default_factory=list)
    status: str = "pending"
    needs_confirmation: bool = False
    source: Optional[Source] = None


@dataclass
class Restriction:
    id: str
    text: str
    topic: Optional[str] = None
    needs_confirmation: bool = False
    source: Optional[Source] = None


@dataclass
class Monitoring:
    id: str
    what: str
    frequency_text: Optional[str] = None
    threshold_text: Optional[str] = None

    needs_confirmation: bool = False
    source: Optional[Source] = None


@dataclass
class WarningSign:
    id: str
    text: str
    action: str
    urgency: str = "contact_care_team"
    needs_confirmation: bool = False
    source: Optional[Source] = None


@dataclass
class DietAdvice:
    id: str
    text: str
    kind: str = "advice"          # "avoid" or "advice"
    needs_confirmation: bool = False
    source: Optional[Source] = None


@dataclass
class RecoveryState:
    patient_id: str
    document_id: str

    discharge_date: Optional[str] = None

    # From the letter's "Patient:" line. Only the first name is kept; None means
    # a caller greets without a name.
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
