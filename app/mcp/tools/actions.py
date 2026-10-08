"""Record task and medication completion for the application-resolved patient context."""

from app.clock import (
    get_current_date,
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
    occurrence_id: str,
) -> dict:
    """
    Mark one occurrence of a recovery task complete today.

    Each repeated task has its own occurrence ID, so
    completing walk 1 never completes walk 2.
    """

    if (
        not occurrence_id
        or not occurrence_id.strip()
    ):
        return error_result(
            code="INVALID_OCCURRENCE_ID",
            message=(
                "A task occurrence is required."
            ),
            next_step=(
                "Check today's tasks and choose an "
                "open occurrence."
            ),
        )

    try:
        result = mark_task_completed(
            patient_context.patient_id,
            occurrence_id.strip(),
            get_current_date(),
        )

    except ValueError as exc:
        return error_result(
            code="TASK_NOT_COMPLETABLE",
            message=str(exc),
            next_step=(
                "Check today's tasks and choose an "
                "open occurrence."
            ),
        )

    if result[
        "already_completed"
    ]:
        message = (
            "That recovery task was already "
            "marked complete."
        )
    else:
        message = (
            "That recovery task is now "
            "marked complete."
        )

    return success_result(
        data=result,
        message=message,
    )


def report_medication_taken_for_context(
    patient_context,
    occurrence_id: str,
) -> dict:
    """
    Record one medication occurrence as taken today.
    """

    if (
        not occurrence_id
        or not occurrence_id.strip()
    ):
        return error_result(
            code="INVALID_OCCURRENCE_ID",
            message=(
                "A medication occurrence is required."
            ),
            next_step=(
                "Check today's medication schedule "
                "and choose the dose."
            ),
        )

    patient_id = (
        patient_context.patient_id
    )

    try:
        result = mark_medication_taken(
            patient_id,
            occurrence_id.strip(),
            get_current_date(),
        )

    except ValueError as exc:
        return error_result(
            code="MEDICATION_NOT_RECORDABLE",
            message=str(exc),
            next_step=(
                "Check today's medications and choose an "
                "open occurrence."
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
