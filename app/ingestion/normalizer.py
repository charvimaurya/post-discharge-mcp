"""Map canonical extraction fields to recovery dataclasses and application-owned IDs/statuses."""

import hashlib
import re
import json
from app.clock import system_now_utc

from app.models.recovery_model import (
    Appointment, Medication, Monitoring, RecoveryState, Restriction,
    DietAdvice, FollowOn, Source, Task, WarningSign,
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


def _significant_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", (text or "").lower()) if len(w) >= 4}


def _same_word(a: str, b: str) -> bool:
    """'exercise' matches 'exercises'."""

    return a.startswith(b) or b.startswith(a)


def _link_follow_ons(tasks: list, raw_tasks: list, document_id) -> None:
    """
    Turn each follow_on's "after_task" words into the id of that task.

    "each set of exercises" -> the "Knee exercises ..." task. A follow_on
    that does not clearly point at exactly one other task is dropped.
    """

    by_description = {t.description: t for t in tasks}

    for raw in raw_tasks:
        follow = raw.get("follow_on")
        task = by_description.get(clean(raw.get("description")))

        if not follow or task is None:
            continue

        wanted = _significant_words(follow.get("after_task"))
        matches = [
            other for other in tasks
            if other is not task
            and any(_same_word(w, d) for w in wanted for d in _significant_words(other.description))
        ]

        if len(matches) != 1:
            continue

        minutes = follow.get("duration_minutes")
        task.follow_on = FollowOn(
            after_task_id=matches[0].id,
            duration_minutes=minutes if isinstance(minutes, int) and minutes > 0 else None,
            source=normalize_source(follow.get("source"), document_id),
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

    _link_follow_ons(tasks, extracted.get("tasks", []), document_id)

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

    diet_advice = []
    for item in extracted.get("diet_advice", []):
        text = clean(item.get("text"))
        if not text:
            continue
        kind = item.get("kind")
        diet_advice.append(DietAdvice(
            id=make_id("diet", text),
            text=text,
            kind=kind if kind in ("avoid", "advice") else "advice",
            # An unknown kind means the model was unsure: hold it for confirmation.
            needs_confirmation=kind not in ("avoid", "advice"),
            source=normalize_source(item.get("source"), document_id),
        ))

    current_timestamp = system_now_utc().isoformat()
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
        diet_advice=diet_advice,
        ingestion_status="processing",
        pending_checkin=None,
        last_updated=current_timestamp,
        timezone="Europe/London",
    )
