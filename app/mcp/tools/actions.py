"""Record task and medication completion for the application-resolved patient context."""

from app.clock import (
    get_current_date,
)

from app.database.recovery_state import (
    get_recovery_state,
    mark_medication_taken,
    mark_task_completed,
    undo_completion,
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
            get_current_date((get_recovery_state(patient_context.patient_id) or {}).get("timezone") or "Europe/London"),
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
            get_current_date((get_recovery_state(patient_context.patient_id) or {}).get("timezone") or "Europe/London"),
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


def undo_report_for_context(
    patient_context,
    occurrence_id: str,
) -> dict:
    """
    Change one of today's saved reports (a dose or a task) back to
    not done, when the patient says it was wrong. History is kept.
    """

    if not occurrence_id or not occurrence_id.strip():
        return error_result(
            code="INVALID_OCCURRENCE_ID",
            message="An occurrence is required.",
            next_step="Use the occurrence_id of the dose or task that was saved by mistake.",
        )

    zone = (get_recovery_state(patient_context.patient_id) or {}).get("timezone") or "Europe/London"

    try:
        result = undo_completion(
            patient_context.patient_id,
            occurrence_id.strip(),
            get_current_date(zone),
        )
    except ValueError as exc:
        return error_result(
            code="NOTHING_TO_UNDO",
            message=str(exc),
            next_step="Check today's tasks and medicines for the item to change back.",
        )

    message = (
        "That report has been changed back to not done."
        if result["undone"]
        else "That item was not marked as done, so nothing changed."
    )

    return success_result(data=result, message=message)
