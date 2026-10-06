"""Map canonical extraction fields to recovery dataclasses and application-owned IDs/statuses."""

import hashlib
import json
from datetime import datetime, timezone

from app.models.recovery_model import (
    Appointment, Medication, Monitoring, RecoveryState, Restriction,
    Source, Task, WarningSign,
)


def make_id(prefix: str, *values) -> str:
    """Build a stable ID from distinct, normalized identity components."""
    normalized = [value.strip().lower() if isinstance(value, str) else value
                  for value in values]
    payload = json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:10]
    return f"{prefix}_{digest}"


def clean(value):
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
    return value


def normalize_source(source_data: dict | None, document_id: str) -> Source | None:
    """Keep document evidence, taking the document ID only from the request."""
    if not source_data:
        return None
    snippet = clean(source_data.get("snippet"))
    if not snippet:
        return None
    return Source(
        document_id=document_id,
        snippet=snippet,
        page=source_data.get("page"),
        read_from_image=bool(source_data.get("read_from_image", False)),
    )


def normalize_recovery_plan(
    extracted: dict,
    patient_id: str,
    document_id: str,
) -> RecoveryState:
    """Normalize the new extraction schema without guessing clinical values."""
    medications = []
    for item in extracted.get("medications", []):
        name = clean(item.get("name"))
        if not name:
            continue
        strength = clean(item.get("strength"))
        dose = clean(item.get("dose"))
        medication_id = make_id("med", name, strength, dose)
        medications.append(Medication(
            id=medication_id,
            name=name,
            strength=strength,
            form=clean(item.get("form")),
            dose=dose,
            site=clean(item.get("site")),
            times_per_day=item.get("times_per_day"),
            time_of_day=list(item.get("time_of_day", [])),
            as_needed=bool(item.get("as_needed", False)),
            as_needed_reason=clean(item.get("as_needed_reason")),
            max_per_day=item.get("max_per_day"),
            instructions=clean(item.get("instructions")),
            duration_text=clean(item.get("duration_text")),
            status="pending",
            needs_confirmation=False,
            source=normalize_source(item.get("source"), document_id),
        ))

    tasks = []
    for item in extracted.get("tasks", []):
        description = clean(item.get("description"))
        if not description:
            continue
        tasks.append(Task(
            id=make_id("task", description, item.get("kind"), item.get("duration_text")),
            description=description,
            kind=item.get("kind", "other"),
            times_per_day=item.get("times_per_day"),
            time_of_day=list(item.get("time_of_day", [])),
            clock_times=list(item.get("clock_times", [])),
            details=clean(item.get("details")),
            duration_text=clean(item.get("duration_text")),
            status="pending",
            needs_confirmation=False,
            source=normalize_source(item.get("source"), document_id),
        ))

    appointments = []
    for item in extracted.get("appointments", []):
        title = clean(item.get("title"))
        if not title:
            continue
        appointments.append(Appointment(
            id=make_id("appt", title, item.get("date"), item.get("time")),
            title=title,
            date=clean(item.get("date")),
            time=clean(item.get("time")),
            location=clean(item.get("location")),
            conflicting_dates=list(item.get("conflicting_dates", [])),
            status="pending",
            needs_confirmation=False,
            source=normalize_source(item.get("source"), document_id),
        ))

    restrictions = []
    for item in extracted.get("restrictions", []):
        text = clean(item.get("text"))
        if not text:
            continue
        restrictions.append(Restriction(
            id=make_id("restriction", text),
            text=text,
            topic=clean(item.get("topic")),
            source=normalize_source(item.get("source"), document_id),
        ))

    monitoring = []
    for item in extracted.get("monitoring", []):
        what = clean(item.get("what"))
        if not what:
            continue
        monitoring.append(Monitoring(
            id=make_id("monitor", what, item.get("frequency_text")),
            what=what,
            frequency_text=clean(item.get("frequency_text")),
            threshold_text=clean(item.get("threshold_text")),
            source=normalize_source(item.get("source"), document_id),
        ))

    warning_signs = []
    for item in extracted.get("warning_signs", []):
        text = clean(item.get("text"))
        action = clean(item.get("action"))
        if not text or not action:
            continue
        warning_signs.append(WarningSign(
            id=make_id("warning", text, action),
            text=text,
            action=action,
            urgency=item.get("urgency", "contact_care_team"),
            source=normalize_source(item.get("source"), document_id),
        ))

    current_timestamp = datetime.now(timezone.utc).isoformat()
    return RecoveryState(
        patient_id=patient_id,
        document_id=document_id,
        discharge_date=clean(extracted.get("discharge_date")),
        medications=medications,
        tasks=tasks,
        appointments=appointments,
        restrictions=restrictions,
        monitoring=monitoring,
        warning_signs=warning_signs,
        ingestion_status="processing",
        pending_checkin=None,
        last_updated=current_timestamp,
        timezone="Europe/London",
    )
