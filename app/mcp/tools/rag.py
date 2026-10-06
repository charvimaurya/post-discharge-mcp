"""Search discharge evidence for the application-resolved patient context."""

from app.mcp.results import (
    error_result,
    success_result,
)

from app.rag.service import (
    search_discharge_instructions,
)


def search_discharge_instructions_for_context(
    patient_context,
    query: str,
) -> dict:

    query = query.strip()

    if not query:
        return error_result(
            code="EMPTY_SEARCH_QUERY",
            message=(
                "I need a question to search the "
                "discharge paperwork."
            ),
            next_step=(
                "Ask what the paperwork says about a "
                "specific topic such as driving."
            ),
        )

    result = search_discharge_instructions(
        query=query,
        patient_id=patient_context.patient_id,
    )

    if not result:
        return error_result(
            code="INSUFFICIENT_EVIDENCE",
            message=(
                "I couldn't find enough evidence in the "
                "discharge paperwork to answer that."
            ),
            next_step=(
                "Check the current recovery plan or ask "
                "about a more specific instruction."
            ),
        )

    return success_result(
        data=result,
        message=(
            "I found relevant evidence in your "
            "discharge paperwork."
        ),
    )
