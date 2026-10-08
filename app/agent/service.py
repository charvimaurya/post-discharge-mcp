"""
Main conversational agent service.

This module coordinates:

    user message
        ↓
    Claude
        ↓
    MCP tool request
        ↓
    MCP result
        ↓
    Claude
        ↓
    patient-facing response
"""

import asyncio
import json
from typing import Any

import boto3

from app import config
from app.agent.evidence import (
    collect_rag_matches,
    select_rag_source,
    split_citation,
)
from app.agent.models import get_agent_model_id
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.safety import (
    expected_write_tool,
    is_ambiguous_medication_write,
    mentions_appointment,
    mentions_date,
    remove_wake_word,
    strip_markdown_emphasis,
)
from app.agent.session import (
    add_message,
    get_history,
)
from app.mcp.client import (
    call_mcp_tool,
    get_mcp_tools,
)


bedrock = boto3.client(
    "bedrock-runtime",
    region_name=config.REGION,
)


# Stops a misbehaving model from looping on tool calls forever.
MAX_TOOL_ROUNDS = 5

# Spoken when the patient reports a completion but nothing of
# that kind is scheduled today (e.g. before discharge).
NOTHING_SCHEDULED_REPLIES = {
    "report_medication_taken": (
        "There's no matching dose scheduled for today."
    ),
    "report_task_completed": (
        "There's no matching task scheduled for today."
    ),
}

# The schedule read that a write tool depends on.
_SCHEDULE_READ_FOR_WRITE = {
    "report_medication_taken": "get_medications",
    "report_task_completed": "get_today_tasks",
}

AMBIGUOUS_MEDICATION_REPLY = (
    "Which medicine did you take? "
    "Tell me the name and I'll mark it as taken."
)


async def build_bedrock_tool_config() -> dict[str, Any]:
    """
    Convert MCP tools/list output into Bedrock's tool format.

    This avoids manually maintaining two copies of each
    tool schema.

    MCP remains the source of truth.
    """

    result = await get_mcp_tools()

    tools = []

    for tool in result.tools:
        tools.append(
            {
                "toolSpec": {
                    "name": tool.name,
                    "description": (
                        tool.description
                        or f"AfterWard tool: {tool.name}"
                    ),
                    "inputSchema": {
                        "json": tool.input_schema
                    },
                }
            }
        )

    return {
        "tools": tools
    }

def build_bedrock_messages(
    history: list[dict],
    current_message: str,
) -> list[dict]:
    """
    Convert our simple session-history format into
    Bedrock Converse messages.
    """

    messages = []

    for item in history:

        role = item["role"]

        # Bedrock expects 'user' or 'assistant'.
        if role not in {"user", "assistant"}:
            continue

        messages.append(
            {
                "role": role,
                "content": [
                    {
                        "text": item["content"]
                    }
                ],
            }
        )

    # Add the newest message last.
    messages.append(
        {
            "role": "user",
            "content": [
                {
                    "text": current_message
                }
            ],
        }
    )

    return messages

def get_structured_tool_result(result) -> Any:
    """
    Extract JSON-like structured content from an MCP result.

    Our AfterWard tools already return structured responses,
    so this is what Claude should receive.
    """

    structured = getattr(
        result,
        "structured_content",
        None,
    )

    if structured is not None:
        return structured

    # The deployed server currently returns the same JSON as a
    # text block instead of structured content.
    for block in getattr(result, "content", None) or []:
        text = getattr(block, "text", None)

        if not text:
            continue

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            continue

    # Defensive fallback if the MCP SDK shape differs.
    return {
        "ok": False,
        "error": {
            "code": "UNSTRUCTURED_TOOL_RESULT",
            "message": "The MCP tool returned no structured content.",
            "next_step": "Try the request again.",
        },
    }

def _medication_names(structured_result: Any) -> list[str]:
    """Medication names from a get_medications / get_recovery_plan result."""

    if not isinstance(structured_result, dict):
        return []

    data = structured_result.get("data")

    if not isinstance(data, dict):
        return []

    return [
        str(medication["name"])
        for medication in data.get("medications") or []
        if isinstance(medication, dict) and medication.get("name")
    ]


def _is_empty_schedule(
    tool_name: str,
    structured_result: Any,
) -> bool:
    """True when a schedule read succeeded but listed nothing today."""

    field = {
        "get_today_tasks": "tasks",
        "get_medications": "medications",
    }.get(tool_name)

    if field is None or not isinstance(structured_result, dict):
        return False

    if not structured_result.get("ok"):
        return False

    data = structured_result.get("data")

    return isinstance(data, dict) and data.get(field) == []


def _build_system_prompt(patient_context: str | None) -> list[dict]:
    """
    Return Bedrock system blocks.

    patient_context is optional extra framing (for example the
    patient's first name). Recovery facts still come from MCP.
    """

    system = [{"text": SYSTEM_PROMPT}]

    if patient_context:
        system.append(
            {
                "text": f"Patient context:\n{patient_context}"
            }
        )

    return system


def _to_tool_result_json(structured_result: Any) -> dict:
    """
    Bedrock requires toolResult JSON to be an object,
    so wrap lists or scalar values.
    """

    if isinstance(structured_result, dict):
        return structured_result

    return {"result": structured_result}


def _extract_text(message: dict) -> str:
    """Join all text blocks from one Bedrock message."""

    return "\n".join(
        block["text"]
        for block in message.get("content", [])
        if "text" in block
    ).strip()


async def chat(
    message: str,
    session_id: str,
    patient_context: str | None = None,
) -> dict[str, Any]:
    """
    Run one conversational turn.

    Returns:
        {
            "response": patient-facing reply,
            "tool_trace": MCP tools Claude called, in order,
            "source": RAG evidence for paperwork answers, or None,
        }
    """

    cleaned_message = remove_wake_word(message)

    tool_trace: list[dict] = []
    source: dict | None = None

    # Every RAG match seen this turn; the source is picked from
    # these once the final reply is known.
    rag_matches: list[dict] = []

    # Medication names from grounded tool results this turn, used
    # to check that a source names the same medicine as the reply.
    entity_names: list[str] = []

    # Deterministic guard: never let the model guess which
    # medication a vague "I took my medicine" refers to.
    if is_ambiguous_medication_write(cleaned_message):
        response_text = AMBIGUOUS_MEDICATION_REPLY

        add_message(session_id, "user", cleaned_message)
        add_message(session_id, "assistant", response_text)

        return {
            "response": response_text,
            "tool_trace": tool_trace,
            "source": source,
        }

    tool_config = await build_bedrock_tool_config()

    messages = build_bedrock_messages(
        get_history(session_id),
        cleaned_message,
    )

    system = _build_system_prompt(patient_context)
    model_id = get_agent_model_id()

    response_text = ""

    required_write = expected_write_tool(cleaned_message)
    write_nudged = False

    # Schedule reads (get_today_tasks / get_medications) that
    # returned no items today. With nothing scheduled no write
    # is possible, so the write check must not push the model
    # to apologise or guess.
    empty_schedules: set[str] = set()

    grounding_nudged = False

    for _ in range(MAX_TOOL_ROUNDS + 1):

        # boto3 is synchronous, so keep it off the event loop.
        response = await asyncio.to_thread(
            bedrock.converse,
            modelId=model_id,
            system=system,
            messages=messages,
            toolConfig=tool_config,
            inferenceConfig={"maxTokens": 512},
        )

        assistant_message = response["output"]["message"]
        messages.append(assistant_message)

        # Claude sometimes writes its reply alongside a tool call
        # and then ends with an empty message, so keep the latest
        # non-empty text from this turn.
        response_text = (
            _extract_text(assistant_message)
            or response_text
        )

        if response["stopReason"] != "tool_use":

            wrote = any(
                item["tool"] == required_write and item["ok"]
                for item in tool_trace
            )

            # The patient reported doing something but Claude
            # only read state. Ask once for the real write.
            if (
                required_write
                and not wrote
                and not write_nudged
                and _SCHEDULE_READ_FOR_WRITE[required_write]
                not in empty_schedules
            ):
                write_nudged = True
                response_text = ""

                messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "text": (
                                    "[System check] The patient reported "
                                    "a completion but you have not called "
                                    f"{required_write}. Call it now with "
                                    "the matching id, even if the item "
                                    "already shows as done. If nothing "
                                    "matching is scheduled for today, say "
                                    "so simply, without apologising. Do "
                                    "not claim anything was recorded."
                                )
                            }
                        ],
                    }
                )
                continue

            # Letter wording comes from RAG, but appointment
            # dates must come from get_recovery_plan in THIS
            # request, never from memory or earlier replies.
            needs_plan = (
                mentions_date(response_text)
                or any(
                    mentions_appointment(match["text"])
                    for match in rag_matches
                )
            )

            read_plan = any(
                item["tool"] == "get_recovery_plan" and item["ok"]
                for item in tool_trace
            )

            if needs_plan and not read_plan and not grounding_nudged:
                grounding_nudged = True
                response_text = ""

                messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "text": (
                                    "[System check] Your answer involves "
                                    "an appointment, review or date, but "
                                    "you have not called get_recovery_plan "
                                    "in this request. Call it now. Keep "
                                    "the letter's wording from "
                                    "search_discharge_instructions, and "
                                    "give any appointment date only from "
                                    "the get_recovery_plan result. If the "
                                    "plan has no such date, say it is not "
                                    "stated. Never use dates from earlier "
                                    "messages."
                                )
                            }
                        ],
                    }
                )
                continue

            break

        tool_results = []

        for block in assistant_message["content"]:

            if "toolUse" not in block:
                continue

            tool_use = block["toolUse"]
            tool_name = tool_use["name"]
            arguments = tool_use.get("input") or {}

            result = await call_mcp_tool(tool_name, arguments)
            structured_result = get_structured_tool_result(result)

            is_error = bool(getattr(result, "is_error", False)) or (
                isinstance(structured_result, dict)
                and structured_result.get("ok") is False
            )

            tool_trace.append(
                {
                    "tool": tool_name,
                    "arguments": arguments,
                    "ok": not is_error,
                }
            )

            entity_names.extend(
                _medication_names(structured_result)
            )

            if _is_empty_schedule(tool_name, structured_result):
                empty_schedules.add(tool_name)

            rag_matches.extend(
                collect_rag_matches(
                    tool_name,
                    structured_result,
                )
            )

            tool_results.append(
                {
                    "toolResult": {
                        "toolUseId": tool_use["toolUseId"],
                        "content": [
                            {
                                "json": _to_tool_result_json(
                                    structured_result
                                )
                            }
                        ],
                        "status": "error" if is_error else "success",
                    }
                }
            )

        messages.append(
            {
                "role": "user",
                "content": tool_results,
            }
        )

    else:
        response_text = (
            "Sorry, I couldn't finish that. "
            "Please try asking again."
        )

    # Deterministic reply: the patient reported doing something,
    # but nothing of that kind is scheduled today, so nothing was
    # (or could be) recorded.
    if (
        required_write
        and _SCHEDULE_READ_FOR_WRITE[required_write] in empty_schedules
        and not any(
            item["tool"] == required_write and item["ok"]
            for item in tool_trace
        )
    ):
        response_text = NOTHING_SCHEDULED_REPLIES[required_write]

    # The evidence tag is for the source only; never speak it.
    response_text, cited_chunk_id, cited_line = split_citation(
        response_text
    )

    if not response_text:
        response_text = (
            "Sorry, I didn't catch that. "
            "Could you say it another way?"
        )

    response_text = strip_markdown_emphasis(response_text)

    # Attach the letter evidence the reply actually used, not
    # the nearest-ranked chunk. None if no evidence was used.
    source = select_rag_source(
        response_text,
        rag_matches,
        context_texts=[cleaned_message] + [
            str(item["arguments"].get("query") or "")
            for item in tool_trace
            if item["tool"] == "search_discharge_instructions"
        ],
        cited_chunk_id=cited_chunk_id,
        cited_line=cited_line,
        entity_names=entity_names,
    )

    # Only plain text goes into session history; tool calls
    # are re-fetched from MCP on every turn.
    add_message(session_id, "user", cleaned_message)
    add_message(session_id, "assistant", response_text)

    return {
        "response": response_text,
        "tool_trace": tool_trace,
        "source": source,
    }
