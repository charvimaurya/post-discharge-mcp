from app.clock import (
    get_current_date,
)

from app.database.recovery_state import (
    get_medications,
    get_recovery_state,
    get_today_tasks,
)

from app.mcp.results import (
    error_result,
    success_result,
)


def get_recovery_plan_for_context(
    patient_context,
) -> dict:
    """
    Return the complete current RecoveryState for the
    authenticated patient.

    This function contains no MCP-specific code so that it
    can be unit tested directly.
    """

    state = get_recovery_state(
        patient_context.patient_id
    )

    if state is None:
        return error_result(
            code="RECOVERY_PLAN_NOT_FOUND",
            message=(
                "I couldn't find a current recovery plan."
            ),
            next_step=(
                "Upload a discharge letter and wait for "
                "processing to finish."
            ),
        )

    return success_result(
        data=state,
        message="I found your current recovery plan.",
    )


def get_today_tasks_for_context(
    patient_context,
) -> dict:
    """
    Return today's recovery tasks for the authenticated
    patient.

    The caller never chooses the date: "today" comes from
    the shared clock so DEMO_FIXED_NOW controls demo time.
    """

    today = get_current_date()

    tasks = get_today_tasks(
        patient_context.patient_id,
        today,
    )

    return success_result(
        data={
            "date": today,
            "tasks": tasks,
        },
        message=(
            f"You have {len(tasks)} recovery "
            "items today."
        ),
    )

def get_medications_for_context(
    patient_context,
) -> dict:

    medications = get_medications(
        patient_context.patient_id
    )

    return success_result(
        data={
            "medications": medications,
        },
        message=(
            f"I found {len(medications)} medications "
            "in your current recovery plan."
        ),
    )