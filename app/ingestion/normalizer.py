"""Convert extracted dictionaries into recovery-plan dataclasses with IDs and source evidence."""

import hashlib
from dataclasses import asdict
from datetime import datetime, timezone

from models.recovery_model import (
    RecoveryState,
    Medication,
    Task,
    Appointment,
    Monitoring,
    Source,
)


def make_id(prefix: str, value: str) -> str:
    normalized = value.strip().lower()

    digest = hashlib.sha256(
        normalized.encode("utf-8")
    ).hexdigest()[:10]

    return f"{prefix}_{digest}"


def clean(value):
    if isinstance(value, str):
        value = value.strip()

        if not value:
            return None

    return value


def normalize_source(item: dict, document_id: str) -> Source:
    source_data = item.get("source") or {}
    return Source(
        document_id=document_id,
        page=source_data.get("page"),
        snippet=source_data.get("snippet"),
    )


def normalize_text_items(items: list, document_id: str) -> list[dict]:
    """Preserve sourced text objects and support earlier string-only output."""
    result = []
    for item in items:
        if isinstance(item, str):
            text = clean(item)
            if not text:
                continue
            item = {"text": text}
        result.append({**item, "source": asdict(normalize_source(item, document_id))})
    return result


def normalize_recovery_plan(
    extracted: dict,
    patient_id: str,
    document_id: str,
) -> RecoveryState:

    medications = []

    for item in extracted.get("medications", []):

        name = clean(item.get("name"))

        if not name:
            continue

        medications.append(
            Medication(
                source=normalize_source(item, document_id),
                id=make_id(
                    "med",
                    f"{name}-{item.get('dose')}-{item.get('frequency')}",
                ),
                name=name,
                dose=clean(item.get("dose")),
                frequency=clean(
                    item.get("frequency")
                ),
                duration=clean(
                    item.get("duration")
                ),
                notes=clean(
                    item.get("notes")
                ),
            )
        )

    tasks = []

    for item in extracted.get("tasks", []):

        description = clean(
            item.get("description")
        )

        if not description:
            continue

        tasks.append(
            Task(
                source=normalize_source(item, document_id),
                id=make_id(
                    "task",
                    f"{description}-{item.get('timing')}",
                ),
                description=description,
                timing=clean(
                    item.get("timing")
                ),
            )
        )

    appointments = []

    for item in extracted.get(
        "appointments",
        [],
    ):

        identifying_text = (
            f"{item.get('with')}-"
            f"{item.get('date')}-"
            f"{item.get('time')}"
        )

        appointments.append(
            Appointment(
                source=normalize_source(item, document_id),
                id=make_id(
                    "appt",
                    identifying_text,
                ),

                with_=clean(
                    item.get("with")
                ),

                date=clean(
                    item.get("date")
                ),

                time=clean(
                    item.get("time")
                ),

                location=clean(
                    item.get("location")
                ),

                status=clean(
                    item.get("status")
                ) or "unknown",

                notes=clean(
                    item.get("notes")
                ),
            )
        )

    monitoring = []

    for item in extracted.get(
        "monitoring",
        [],
    ):

        what = clean(
            item.get("what")
        )

        if not what:
            continue

        monitoring.append(
            Monitoring(
                source=normalize_source(item, document_id),
                id=make_id(
                    "monitor",
                    what,
                ),

                what=what,

                how_often=clean(
                    item.get("how_often")
                ),

                threshold=clean(
                    item.get("threshold")
                ),
            )
        )

    return RecoveryState(

        patient_id=patient_id,

        document_id=document_id,

        discharge_date=clean(
            extracted.get("discharge_date")
        ),

        medications=medications,

        tasks=tasks,

        appointments=appointments,

        restrictions=normalize_text_items(extracted.get("restrictions", []), document_id),

        monitoring=monitoring,

        warning_signs=normalize_text_items(extracted.get("warning_signs", []), document_id),

        ingestion_status="processing",

        pending_checkin=None,

        last_updated=datetime.now(
            timezone.utc
        ).isoformat(),
    )
