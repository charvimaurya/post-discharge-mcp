from models.recovery_model import RecoveryState


def contains_uncertainty(
    value: str | None,
) -> bool:
    if not value:
        return False
    lowered = value.lower()
    return (
        "[?" in value
        or "[unreadable]" in lowered
    )


def validate_recovery_plan(
    state: RecoveryState,
) -> RecoveryState:

    validate_medications(state)
    validate_tasks(state)
    validate_appointments(state)
    validate_monitoring(state)

    state.ingestion_status = "ready"

    return state


def validate_medications(
    state: RecoveryState,
):

    for med in state.medications:

        if not med.name:
            med.needs_confirmation = True

        # Example:
        # medicine exists but dose/frequency is unclear.
        #
        # Do not necessarily reject the medication,
        # just mark it uncertain.

        if not med.dose:
            med.needs_confirmation = True

        if not med.frequency:
            med.needs_confirmation = True

        values = [med.name, med.dose, med.frequency, med.duration, med.notes]
        if any(contains_uncertainty(value) for value in values):
            med.needs_confirmation = True


def validate_tasks(
    state: RecoveryState,
):

    for task in state.tasks:

        if not task.description:
            task.needs_confirmation = True

        if contains_uncertainty(task.description):
            task.needs_confirmation = True

        if contains_uncertainty(task.timing):
            task.needs_confirmation = True


def validate_appointments(
    state: RecoveryState,
):

    for appointment in state.appointments:

        values = [
            appointment.with_,
            appointment.date,
            appointment.time,
            appointment.location,
            appointment.notes,
        ]
        if any(contains_uncertainty(value) for value in values):
            appointment.needs_confirmation = True

        if appointment.status not in {
            "booked",
            "to_arrange",
            "unknown",
        }:
            appointment.status = "unknown"
            appointment.needs_confirmation = True


def validate_monitoring(
    state: RecoveryState,
):

    for item in state.monitoring:

        if not item.what:
            item.needs_confirmation = True

        values = [item.what, item.how_often, item.threshold]
        if any(contains_uncertainty(value) for value in values):
            item.needs_confirmation = True
