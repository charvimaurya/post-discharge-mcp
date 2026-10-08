from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from starlette.requests import Request
from starlette.responses import JSONResponse


from app.mcp.context import (
    get_current_patient_context,
)

from app.mcp.tools.actions import (
    report_medication_taken_for_context,
    report_task_completed_for_context,
)

from app.mcp.tools.rag import (
    search_discharge_instructions_for_context,
)

from app.mcp.tools.recovery import (
    get_medications_for_context,
    get_recovery_plan_for_context,
    get_today_tasks_for_context,
)


mcp = MCPServer(
    "AfterWard"
)


@mcp.tool(
    name="get_recovery_plan",
    description=(
        "Returns the authenticated patient's complete current "
        "recovery plan, including medications, tasks, "
        "appointments, restrictions, monitoring, warning signs "
        "and source evidence. Use this for questions about the "
        "patient's current recovery plan or when a paperwork "
        "search has insufficient evidence."
    ),
    annotations=ToolAnnotations(
        read_only_hint=True,
    ),
)
async def get_recovery_plan() -> dict:
    context = get_current_patient_context()

    return get_recovery_plan_for_context(
        context
    )


@mcp.tool(
    name="get_today_tasks",
    description=(
        "Get the patient's current recovery tasks for today. "
        "Today is determined by the server; do not pass a date. "
        "Use this for questions like 'what do I need to do "
        "today?', and whenever the patient asks what is left, "
        "what is next, what they still need to do, what remains "
        "today, or what they have not completed yet. Always use "
        "this tool for those questions because task completion "
        "state may have changed since the previous conversation "
        "turn."
    ),
    annotations=ToolAnnotations(
        read_only_hint=True,
    ),
)
async def get_today_tasks() -> dict:
    context = get_current_patient_context()

    return get_today_tasks_for_context(
        context
    )


@mcp.tool(
    name="get_medications",
    description=(
        "Returns the authenticated patient's medication "
        "schedule, status and uncertainty information. "
        "Use this for questions about what medicines are "
        "in the current recovery plan or which medicines "
        "are scheduled today."
    ),
    annotations=ToolAnnotations(
        read_only_hint=True,
    ),
)
async def get_medications() -> dict:

    context = get_current_patient_context()

    return get_medications_for_context(
        context
    )


@mcp.tool(
    name="search_discharge_instructions",
    description=(
        "Searches the authenticated patient's original "
        "discharge paperwork and returns relevant source "
        "evidence. Use this when the patient asks what their "
        "letter, paperwork or discharge instructions said "
        "about a topic. Do not use it for current completion "
        "status; use recovery-state tools for that."
    ),
    annotations=ToolAnnotations(
        read_only_hint=True,
    ),
)
async def search_discharge_instructions(
    query: str,
) -> dict:

    context = get_current_patient_context()

    return search_discharge_instructions_for_context(
        context,
        query,
    )


@mcp.tool(
    name="report_task_completed",
    description=(
        "Use this tool when the patient reports completing a "
        "recovery task such as a walk, exercise, weighing, or "
        "monitoring task. This is the ONLY tool that records task "
        "completion; reading get_today_tasks does not record "
        "anything. Pass the occurrence_id from get_today_tasks. "
        "Each occurrence is recorded independently, so completing "
        "one walk does not complete another walk later in the day."
    ),
    annotations=ToolAnnotations(
        idempotent_hint=True,
    ),
)
async def report_task_completed(
    occurrence_id: str,
) -> dict:

    context = get_current_patient_context()

    return report_task_completed_for_context(
        context,
        occurrence_id,
    )


@mcp.tool(
    name="report_medication_taken",
    description=(
        "Use this tool when the patient reports that they have "
        "taken a specific medication dose. This is the ONLY tool "
        "that records medication completion; reading "
        "get_medications does not record anything. Pass the "
        "occurrence_id from get_medications. Use this only when "
        "the patient clearly identifies the medication they have "
        "taken. Each dose is recorded independently, so recording "
        "the morning dose does not record a later dose that day."
    ),
    annotations=ToolAnnotations(
        idempotent_hint=True,
    ),
)
async def report_medication_taken(
    occurrence_id: str,
) -> dict:

    context = get_current_patient_context()

    return report_medication_taken_for_context(
        context,
        occurrence_id,
    )

@mcp.custom_route(
    "/health",
    methods=["GET"],
)
async def health(
    request: Request,
):

    return JSONResponse(
        {
            "status": "ok",
            "service": "AfterWard MCP",
        }
    )
