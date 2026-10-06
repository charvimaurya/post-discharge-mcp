"""Record task and medication completion for the application-resolved patient context."""

from app.clock import (
    get_current_date,
)

from app.database.event_history import (
    build_idempotency_key,
)

from app.database.recovery_state import (
    mark_medication_taken,
    mark_task_completed,
)

from app.mcp.results import (
    error_result,
    success_result,
)


def report_task_completed_for_context(
    patient_context,
    task_id: str,
) -> dict:
    """
    Mark one recovery task complete for today.

    The occurrence key comes from the shared clock, so
    repeating the same report on the same day is idempotent.
    """

    if not task_id or not task_id.strip():
        return error_result(
            code="INVALID_TASK_ID",
            message="A task is required.",
            next_step=(
                "Choose one of today's open recovery tasks."
            ),
        )

    try:
        result = mark_task_completed(
            patient_context.patient_id,
            task_id,
            get_current_date(),
        )

    except ValueError as exc:
        return error_result(
            code="TASK_NOT_COMPLETABLE",
            message=str(exc),
            next_step=(
                "Check today's tasks and choose an "
                "open task."
            ),
        )

    if result["already_completed"]:
        message = "That recovery task was already marked complete."
    else:
        message = "That recovery task is now marked complete."

    return success_result(
        data=result,
        message=message,
    )


def report_medication_taken_for_context(
    patient_context,
    medication_id: str,
) -> dict:
    """
    Record one medication as taken for today.

    The idempotency key is built from the patient, the
    medication and today's date from the shared clock.
    """

    if not medication_id or not medication_id.strip():
        return error_result(
            code="INVALID_MEDICATION_ID",
            message="A medication is required.",
            next_step=(
                "Check today's medication schedule "
                "and choose the medicine."
            ),
        )

    patient_id = patient_context.patient_id

    try:
        result = mark_medication_taken(
            patient_id,
            medication_id,
            build_idempotency_key(
                patient_id,
                medication_id,
                get_current_date(),
            ),
        )

    except ValueError as exc:
        return error_result(
            code="MEDICATION_NOT_RECORDABLE",
            message=str(exc),
            next_step=(
                "Check the medication schedule and "
                "choose an open medication."
            ),
        )

    if result["already_completed"]:
        message = "That medication was already recorded as taken."
    else:
        message = "I've recorded that medication as taken."

    return success_result(
        data=result,
        message=message,
    )
