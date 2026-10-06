"""Flag missing or uncertain recovery instructions and mark the locally validated state ready."""

from models.recovery_model import RecoveryState


def contains_uncertainty(value: str | None) -> bool:
    if not value:
        return False
    return "[?" in value or "[unreadable]" in value.lower()


def validate_recovery_plan(state: RecoveryState) -> RecoveryState:
    validate_medications(state)
    validate_tasks(state)
    validate_appointments(state)
    validate_restrictions(state)
    validate_monitoring(state)
    validate_warning_signs(state)
    state.ingestion_status = "ready"
    return state


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
