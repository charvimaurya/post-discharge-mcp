"""Flag missing or uncertain recovery instructions and mark the locally validated state ready."""

import re

from discharge_letter_check.models import RecoveryState


def contains_uncertainty(value: str | None) -> bool:
    if not value:
        return False
    return "[?" in value or "[unreadable]" in value.lower()


def validate_recovery_plan(
    state: RecoveryState,
    document_text: str | None = None,
) -> RecoveryState:
    validate_medications(state)
    validate_tasks(state)
    validate_appointments(state)
    validate_restrictions(state)
    validate_monitoring(state)
    validate_warning_signs(state)
    validate_diet_advice(state, document_text)
    validate_follow_ons(state, document_text)
    state.ingestion_status = "ready"
    return state


def _words_only(text: str) -> str:
    """Lower-case words only, so a PDF line break does not break a match."""

    return " ".join(re.findall(r"[a-z0-9]+", (text or "").lower()))


def validate_follow_ons(state: RecoveryState, document_text: str | None = None):
    """
    Keep a follow_on only if its snippet is in the letter word for word, its
    minutes are written in that snippet, and it points at another real task.
    Otherwise drop it: a caller may quote it to the patient.
    """

    task_ids = {task.id for task in state.tasks}
    letter = f" {_words_only(document_text)} " if document_text is not None else None

    for task in state.tasks:
        follow = task.follow_on

        if follow is None:
            continue

        snippet = _words_only(follow.source.snippet if follow.source else "")
        keep = (
            bool(snippet)
            and follow.after_task_id in task_ids
            and follow.after_task_id != task.id
            and follow.duration_minutes is not None
            and f" {follow.duration_minutes} minutes" in f" {snippet}"
            and (letter is None or f" {snippet} " in letter)
        )

        if not keep:
            task.follow_on = None


def validate_diet_advice(state: RecoveryState, document_text: str | None = None):
    """
    Keep only diet lines found word for word in the letter, and flag unclear ones.

    A caller may quote these lines to the patient, so a line the model
    reworded or invented is dropped rather than shown.
    """

    if document_text is not None:
        letter = f" {_words_only(document_text)} "
        state.diet_advice = [
            advice for advice in state.diet_advice
            if _words_only(advice.text) and f" {_words_only(advice.text)} " in letter
        ]

    for advice in state.diet_advice:
        if contains_uncertainty(advice.text):
            advice.needs_confirmation = True


def validate_medications(state: RecoveryState):
    for medication in state.medications:
        if not medication.name:
            medication.needs_confirmation = True
        # Optional details may be absent; flag explicit uncertainty, not absence.
        fields_to_check = [
            medication.name, medication.strength, medication.dose,
            medication.form, medication.site, medication.instructions,
            medication.duration_text, medication.as_needed_reason,
        ]
        if any(contains_uncertainty(value) for value in fields_to_check):
            medication.needs_confirmation = True


def validate_tasks(state: RecoveryState):
    for task in state.tasks:
        if not task.description:
            task.needs_confirmation = True
        values = [task.description, task.details, task.duration_text]
        if any(contains_uncertainty(value) for value in values):
            task.needs_confirmation = True


def validate_appointments(state: RecoveryState):
    for appointment in state.appointments:
        if not appointment.title:
            appointment.needs_confirmation = True
        values = [appointment.title, appointment.date, appointment.time, appointment.location]
        if any(contains_uncertainty(value) for value in values):
            appointment.needs_confirmation = True
        # Preserve all dates for review instead of selecting one or rewriting status.
        if appointment.conflicting_dates:
            appointment.needs_confirmation = True


def validate_restrictions(state: RecoveryState):
    for restriction in state.restrictions:
        if not restriction.text:
            restriction.needs_confirmation = True
        if any(contains_uncertainty(value) for value in [restriction.text, restriction.topic]):
            restriction.needs_confirmation = True


def validate_monitoring(state: RecoveryState):
    for monitoring in state.monitoring:
        if not monitoring.what:
            monitoring.needs_confirmation = True
        values = [monitoring.what, monitoring.frequency_text, monitoring.threshold_text]
        if any(contains_uncertainty(value) for value in values):
            monitoring.needs_confirmation = True


def validate_warning_signs(state: RecoveryState):
    for warning in state.warning_signs:
        if not warning.text or not warning.action:
            warning.needs_confirmation = True
        if any(contains_uncertainty(value) for value in [warning.text, warning.action]):
            warning.needs_confirmation = True
        if warning.urgency not in {"contact_care_team", "emergency"}:
            warning.needs_confirmation = True
