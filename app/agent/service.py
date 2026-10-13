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
import re
from contextvars import ContextVar
from datetime import timedelta
from typing import Any, Callable

import boto3

from app import config
from app.agent.completion_replies import (
    WRITE_FAILED_REPLY,
    medicine_name,
    after_completion_reply,
    also_completed,
    already_done_reply,
    ask_reply,
    ask_which_medicine,
    completed_opener,
    describe,
    after_that_sentence,
    day_summary,
    next_step_sentence,
    not_yet_reply,
    reminder_ack_reply,
    saved_doses_reply,
    short_dose_reply,
    undo_question,
    undone_reply,
    which_one_question,
    whats_next_reply,
)
from app.agent.dose_answers import (
    _mentions as dose_mentions,
    count_without_name,
    stated_count,
    _tokens as dose_tokens,
    is_short_dose,
    parse_dose_answer,
    write_refusal,
)
from app.agent.next_up import build_next_up, build_steps, describe_for_model, step_ids
from app.agent.food import (
    ATE,
    NOT_YET,
    PLAN,
    classify_food_message,
    diet_reply,
    diet_source,
    food_question_reply,
    foods_named,
    is_food_message,
    meal_medicines_reminder,
    meal_medicines_question,
    meals_named,
    medicines_for_meal,
)
from app.agent.evidence import (
    _blocks as letter_blocks,
    _sentences as letter_sentences,
    _source as evidence_source,
    collect_rag_matches,
    select_rag_source,
    split_citation,
    split_letter_items,
)
from app.agent.models import get_agent_model_id
from app.agent.occurrence_resolver import (
    everyday_name,
    item_id,
    item_name,
    items_mentioned,
    resolve_occurrence,
    resolve_vague_medication,
)
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.safety import (
    asked_about_completion,
    asks_after_that,
    asks_whats_left_today,
    expected_write_tool,
    is_acknowledgement,
    is_affirmative,
    is_correction,
    is_ambiguous_medication_write,
    is_missed_dose_question,
    is_negative_report,
    is_next_up_question,
    is_permission_question,
    mentions_appointment,
    mentions_date,
    remove_hollow_openers,
    remove_unasked_prompts,
    remove_screen_references,
    remove_wake_word,
    strip_markdown_emphasis,
    tidy_reply,
)
from app.clock import get_patient_datetime
from app.reminders import config as checkin_config
from app.reminders.engine import recheck_text
from app.reminders.text import short_task_name, time_to_words
from app.agent.session import (
    add_message,
    get_history,
    get_last_prompt,
    get_step_pointer,
    pop_last_saved,
    pop_offer,
    set_last_prompt,
    set_last_saved,
    set_offer,
    set_step_pointer,
)
from app.agent.intent import Intent, classify_intent
from app.agent.symptoms import (
    find_symptom,
    letter_sentence_reply,
    match_letter_sentence,
    match_warning_sign,
    no_match_reply,
    sign_source,
    warning_sign_reply,
    help_actions,
)
from app.mcp.client import (
    call_mcp_tool,
    get_mcp_tools,
)
from app.observability.log import Timer, hash_session, service_log


bedrock = boto3.client(
    "bedrock-runtime",
    region_name=config.REGION,
)

log = service_log("agent")


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


def _build_system_prompt(
    patient_context: str | None,
    facts: str | None = None,
) -> list[dict]:
    """
    Return Bedrock system blocks.

    patient_context is optional extra framing (for example the
    patient's first name). facts is this turn's server-side state:
    the time now, any waiting reminder and today's occurrences.
    """

    system = [{"text": SYSTEM_PROMPT}]

    if patient_context:
        system.append(
            {
                "text": f"Patient context:\n{patient_context}"
            }
        )

    if facts:
        system.append({"text": facts})

    return system


# Read before every turn so the agent knows today's state and the
# resolver can pick an occurrence without asking.
_FACT_READS = (
    ("get_today_tasks", "tasks"),
    ("get_medications", "medications"),
)


async def _load_today(tool_trace: list[dict]) -> dict[str, list] | None:
    """
    Today's task and medicine occurrences, through MCP.

    Each read is added to tool_trace. Returns None if either read
    fails; the turn then continues without these facts.
    """

    today: dict[str, list] = {}

    for tool_name, field in _FACT_READS:
        try:
            result = get_structured_tool_result(await call_mcp_tool(tool_name, {}))
        except Exception:
            tool_trace.append({"tool": tool_name, "arguments": {}, "ok": False})
            return None

        ok = isinstance(result, dict) and result.get("ok") is True
        tool_trace.append({"tool": tool_name, "arguments": {}, "ok": ok})

        data = result.get("data") if ok else None

        if not isinstance(data, dict) or not isinstance(data.get(field), list):
            return None

        today[field] = data[field]

    return today


def _spoken_clock(now) -> str:
    return f"{now.hour % 12 or 12}:{now.minute:02d} {'am' if now.hour < 12 else 'pm'}"


def _describe_facts(
    today: dict[str, list],
    now,
    pending_checkin: dict | None,
    first_name: str | None,
    quiet: bool = False,
) -> str:
    """
    The facts block given to the model on every turn.

    quiet: she did not report anything or ask about her plan, so the model
    is not shown what is next and is told not to bring it up.
    """

    def line(o: dict) -> str:
        name = o.get("name") or o.get("description") or "item"
        dose = f", {o['dose']}" if o.get("dose") else ""
        time = o.get("clock_time") or "no set time"
        part = o.get("time_of_day_label") or "-"
        return f"  - {o.get('occurrence_id')} | {name}{dose} | {time} | {part}"

    everything = today["tasks"] + today["medications"]
    scheduled = [o for o in everything if not o.get("as_needed")]
    pending = [o for o in scheduled if o.get("status") != "completed"]
    done = [o for o in scheduled if o.get("status") == "completed"]
    as_needed = sorted({str(o.get("name")) for o in everything if o.get("as_needed")})

    reminder = "none"

    if pending_checkin:
        reminded = next(
            (o for o in everything if o.get("occurrence_id") == pending_checkin.get("occurrence_id")),
            None,
        )
        clock = pending_checkin.get("clock_time")
        what = describe(reminded) if reminded else "an item"
        when = f", due at {time_to_words(str(clock))}" if clock else ""
        reminder = f"{what}{when} (occurrence_id {pending_checkin.get('occurrence_id')})"

    parts = [
        "Current facts from the server. Trust these; never ask the patient for them.",
        f"- Patient's first name: {first_name or 'not known'}",
        f"- Time now: {_spoken_clock(now)} on {now:%A} {now.day} {now:%B} (patient's local time)",
        f"- Waiting reminder: {reminder}",
        "- Still to do today (occurrence_id | item | clock time | time of day):",
        *([line(o) for o in pending] or ["  - nothing"]),
        "- Already done today:",
        *([line(o) for o in done] or ["  - nothing"]),
        f"- Only if needed (never due): {', '.join(as_needed) or 'none'}",
    ]

    if quiet:
        parts.append(
            "- She did not ask about her plan. Answer only what she said. Do NOT mention "
            "medicines, tasks, reminders or what is next, and do not ask whether she has taken anything."
        )
    else:
        parts += [
            "- Next up, in order (due now first; medicines use the letter's wording):",
            describe_for_model(build_next_up(today["tasks"], today["medications"], now)),
        ]

    return "\n".join(parts)


async def _resolve_completion(
    message: str,
    required_write: str,
    today: dict[str, list],
    now,
    pending_checkin: dict | None,
    first_name: str | None,
    tool_trace: list[dict],
    extras: dict | None = None,
) -> str | None:
    """
    Handle "I'm back from my walk" in code: pick the occurrence,
    write it, and return the spoken reply. None hands the turn to
    the model (the patient named a time, or the item is unclear).
    """

    is_medication = required_write == "report_medication_taken"
    occurrences = today["medications" if is_medication else "tasks"]

    resolution = resolve_occurrence(message, occurrences, now, pending_checkin)

    if resolution.action == "model":
        return None

    if resolution.action == "nothing":
        return NOTHING_SCHEDULED_REPLIES[required_write]

    if resolution.action == "ask":
        return ask_reply(resolution.choices)

    if resolution.action == "already_done":
        return already_done_reply(resolution.done, resolution.next_up, first_name)

    occurrence = resolution.occurrence

    if is_medication and is_short_dose(message, occurrence) is not None:
        tool_trace.append(_blocked_note(required_write, {"occurrence_id": occurrence["occurrence_id"]})
                          | {"note": "Not recorded: less than the dose in the letter."})
        return short_dose_reply(occurrence)

    if not await _write(required_write, occurrence, tool_trace):
        return _failed_write_reply()

    return _after_write(occurrence, is_medication, today, now, first_name, tool_trace, extras)


# "I did my walk and I took my paracetamol": the parts of one report.
_REPORT_PARTS = re.compile(r"\s*(?:,|;|&|\band then\b|\bthen\b|\band also\b|\balso\b|\band\b|\bplus\b|\bbut\b)\s*")


def _compound_parts(message: str, today: dict[str, list]) -> list[tuple[str, bool]]:
    """
    The parts of a report that names BOTH a task and a medicine, as (text, is_medication).

    Empty unless she named at least one of each, so every other report keeps
    its usual path. Each part is the piece of her sentence that names the item.
    """

    parts: list[tuple[str, bool]] = []
    seen: set[str] = set()

    for piece in _REPORT_PARTS.split(message):
        for is_medication, field in ((False, "tasks"), (True, "medications")):
            for occurrence in items_mentioned(piece, today[field]):
                if item_id(occurrence) not in seen:
                    seen.add(item_id(occurrence))
                    parts.append((piece, is_medication))

    kinds = {is_medication for _, is_medication in parts}

    return parts if kinds == {True, False} else []


async def _compound_report(
    parts: list[tuple[str, bool]],
    today: dict[str, list],
    now,
    pending_checkin: dict | None,
    first_name: str | None,
    tool_trace: list[dict],
    extras: dict,
) -> str | None:
    """
    Record every part of "I did my walk and I took my paracetamol".

    Each part is resolved and written like a report on its own, so the same
    checks apply (which occurrence, the full dose). The reply names everything
    that was saved, then gives the next step once. If any part is unclear,
    nothing is written and the model is not asked to guess: None.
    """

    planned = []

    for text, is_medication in parts:
        resolution = resolve_occurrence(text, today["medications" if is_medication else "tasks"], now, pending_checkin)

        if resolution.action == "already_done":
            continue
        if resolution.action != "record":
            return None
        if is_medication and is_short_dose(text, resolution.occurrence) is not None:
            return None

        planned.append((resolution.occurrence, is_medication))

    if len(planned) < 2:
        return None

    # A task the letter follows with something (an ice pack) goes last, so that is said last.
    planned.sort(key=lambda item: 1 if not item[1] and _follow_on_after(today, item[0]) else 0)

    said = []

    for index, (occurrence, is_medication) in enumerate(planned):
        tool_name = "report_medication_taken" if is_medication else "report_task_completed"

        if not await _write(tool_name, occurrence, tool_trace):
            return " ".join(said + [_failed_write_reply()]) if said else _failed_write_reply()

        if index < len(planned) - 1:
            _mark_done(today, occurrence["occurrence_id"])
            said.append(
                completed_opener(occurrence, first_name, is_medication) if index == 0
                else also_completed(occurrence, is_medication)
            )

    last, last_is_medication = planned[-1]
    ending = _after_write(last, last_is_medication, today, now, None, tool_trace, extras)
    # The last one's own "Thank you, ..." becomes "I've also marked ...".
    ending = ending.replace(completed_opener(last, None, last_is_medication), also_completed(last, last_is_medication), 1)

    return " ".join(said + [ending])


# This turn's message and the question she is answering, for the write
# guard. Set at the start of chat(); read only by _execute_tool.
_TURN: ContextVar[dict] = ContextVar("afterward_turn", default={})


def _refusal_for(tool_name: str, arguments: dict) -> tuple[str, str, dict] | None:
    """(code, note, dose) if this write must be refused, else None. Medicines only."""

    if tool_name != "report_medication_taken":
        return None

    turn = _TURN.get()
    medications = (turn.get("today") or {}).get("medications") or []
    dose = next((m for m in medications if m.get("occurrence_id") == arguments.get("occurrence_id")), None)

    if dose is None:
        return None

    # One dose per medicine, to tell "she named a different medicine".
    others = list({m.get("medication_id"): m for m in medications}.values())
    message = turn.get("message") or ""
    refusal = write_refusal(message, dose, turn.get("question"), is_negative_report(message), others)

    return (*refusal, dose) if refusal else None


async def _execute_tool(tool_name: str, arguments: dict, tool_trace: list[dict]):
    """
    The ONE place a tool call is executed, for code paths and the model alike.

    Every report_medication_taken is checked here first against her latest
    message and the question she is answering (app.agent.dose_answers.
    write_refusal). A refused write is never sent to MCP: it is shown in
    tool_trace as blocked, and the result tells the model to ask instead.

    Returns (structured_result, ok, raw_result).
    """

    refusal = _refusal_for(tool_name, arguments)

    if refusal is not None:
        code, note, dose = refusal
        tool_trace.append({"tool": tool_name, "arguments": arguments, "ok": False, "blocked": True, "note": note})
        _TURN.get().setdefault("blocked", []).append((code, dose))
        log("write_blocked", tool=tool_name, kind="write", reason=code, blocked_writes=1)
        next_step = {
            "which": "Do not record anything. Ask which medicine she took, by name.",
            "short": "Do not record anything. Tell her the letter's dose and ask her to say when she has taken the full dose.",
            "not_taken": "Do not record anything. Say kindly that it is still in today's plan.",
        }[code]
        return {"ok": False, "error": {"code": f"NOT_RECORDED_{code.upper()}", "message": note,
                                       "next_step": next_step}}, False, None

    try:
        raw = await call_mcp_tool(tool_name, arguments)
        structured = get_structured_tool_result(raw)
    except Exception:
        tool_trace.append({"tool": tool_name, "arguments": arguments, "ok": False})
        return None, False, None

    is_error = bool(getattr(raw, "is_error", False)) or (
        isinstance(structured, dict) and structured.get("ok") is False
    )
    tool_trace.append({"tool": tool_name, "arguments": arguments, "ok": not is_error})

    return structured, not is_error, raw


def _refused_write_reply() -> str | None:
    """
    The reply after a medicine write was refused this turn, or None if none was.

    "which"     -> "Which one did you take: your paracetamol or your blood thinner?"
    "short"     -> the letter's dose; nothing marked as done
    "not_taken" -> "still in today's plan"
    Never "I've noted" or "marked as taken".
    """

    turn = _TURN.get()
    blocked = turn.get("blocked") or []

    if not blocked:
        return None

    codes = {code for code, _ in blocked}
    doses = list({dose.get("medication_id"): dose for _, dose in blocked}.values())

    if "not_taken" in codes:
        return not_yet_reply(doses, turn.get("first_name"), True)

    if "short" in codes:
        return short_dose_reply(next(dose for code, dose in blocked if code == "short"))

    # "which": ask, naming the medicines due now, and remember any count she gave.
    today, now = turn.get("today") or {}, turn.get("now")
    choices = doses
    if now is not None and len(choices) < 2:
        resolution = resolve_vague_medication(today.get("medications") or [], now, None)
        if resolution.action == "ask":
            choices = resolution.choices
    numbers = [int(w) if w.isdigit() else {"one": 1, "two": 2, "three": 3}.get(w)
               for w in dose_tokens(turn.get("message") or "") if w.isdigit() or w in ("one", "two", "three")]
    set_offer(turn.get("session_id"), {
        "kind": "which_medicines",
        "occurrence_ids": [d["occurrence_id"] for d in choices],
        "stated": numbers[0] if len(numbers) == 1 else (1 if " a tablet" in f" {(turn.get('message') or '').lower()}" else None),
    })

    return which_one_question(choices)


def _failed_write_reply() -> str:
    """After _write returned False: the refusal reply if the guard refused it, else 'couldn't record'."""

    return _refused_write_reply() or WRITE_FAILED_REPLY


async def _write(tool_name: str, occurrence: dict, tool_trace: list[dict]) -> bool:
    """Call one report_* tool for one occurrence (through the guard); True only if saved."""

    _, ok, _ = await _execute_tool(tool_name, {"occurrence_id": occurrence["occurrence_id"]}, tool_trace)

    return ok


def _next_up(today: dict[str, list], now, tool_trace: list[dict]):
    """Today's pending tasks and medicines, in order, and the one or two to name next."""

    items = build_next_up(today["tasks"], today["medications"], now)
    tool_trace.append(
        {
            "tool": "next_up",
            "arguments": {},
            "ok": True,
            "note": "Worked out from get_today_tasks and get_medications.",
        }
    )

    return items, build_steps(items)


def _mark_done(today: dict[str, list], occurrence_id: str) -> dict | None:
    """Mark one occurrence completed in this turn's copy of today; return it."""

    for field in ("tasks", "medications"):
        for occurrence in today[field]:
            if occurrence.get("occurrence_id") == occurrence_id:
                occurrence["status"] = "completed"
                return occurrence

    return None


_ICE_PACK = re.compile(r"^ice pack on (?:the|your) ([a-z]+)", re.IGNORECASE)


def _follow_on_after(today: dict[str, list], done: dict) -> tuple[dict, dict] | None:
    """The task the letter says to do straight after `done`, and its follow_on, if any."""

    done_task = done.get("task_id")

    if not done_task:
        return None

    for task in today["tasks"]:
        follow = task.get("follow_on") or {}
        if follow.get("after_task_id") == done_task and follow.get("duration_minutes"):
            return task, follow

    return None


def _follow_on_wording(task: dict, follow: dict, first_name: str | None) -> tuple[str, str, str]:
    """
    (what to do now, the question, the later check-in text), from fixed templates.

    "Ice pack on the knee for 20 minutes ..." gets the ice-pack wording;
    anything else quotes the letter's own sentence.
    """

    minutes = int(follow["duration_minutes"])
    snippet = str((follow.get("source") or {}).get("snippet") or task.get("description") or "").strip()
    ice = _ICE_PACK.match(str(task.get("description") or ""))

    if ice:
        part = ice.group(1).lower()
        return (
            f"Your letter says to put an ice pack on your {part} for {minutes} minutes now.",
            "Shall I remind you when it's time to take it off?",
            f"Time to take the ice pack off your {part}{_who(first_name)}.",
        )

    return (
        f"Your letter says: {snippet}",
        f"Shall I remind you when the {minutes} minutes are up?",
        f"Your {minutes} minutes are up{_who(first_name)}.",
    )


def _follow_on_source(task: dict, follow: dict) -> dict | None:
    """The letter sentence, for the letter panel."""

    source = follow.get("source") or {}
    snippet = source.get("snippet")

    if not snippet:
        return None

    return {
        "document_id": source.get("document_id"),
        "page": source.get("page"),
        "chunk_id": None,
        "section": None,
        "text": snippet,
        "highlight": snippet,
        "passage": snippet,
        "highlighted_line": snippet,
    }


def _after_write(
    occurrence: dict,
    is_medication: bool,
    today: dict[str, list],
    now,
    first_name: str | None,
    tool_trace: list[dict],
    extras: dict | None = None,
) -> str:
    """
    The reply after a saved report: well done, then what is next today.

    If the letter says to do something straight after this task (an ice
    pack after exercises), say that instead and offer to remind her when
    it is time to stop. extras collects the letter source and the offer.
    """

    _mark_done(today, occurrence["occurrence_id"])

    follow = None if is_medication else _follow_on_after(today, occurrence)

    if follow is not None and extras is not None:
        task, details = follow
        now_text, question, later_text = _follow_on_wording(task, details, first_name)
        extras["source"] = _follow_on_source(task, details)
        extras["offer"] = {
            "kind": "follow_on",
            "occurrence_id": task.get("occurrence_id"),
            "after_occurrence_id": occurrence["occurrence_id"],
            "minutes": int(details["duration_minutes"]),
            "text": later_text,
        }
        opener = completed_opener(occurrence, first_name, False)
        return f"{opener} {now_text} {question}"

    _, steps = _next_up(today, now, tool_trace)

    return after_completion_reply(occurrence, first_name, is_medication, steps)


async def _answer_follow_on_offer(
    message: str,
    offer: dict,
    now,
    first_name: str | None,
    schedule_checkin: Callable[[dict], None] | None,
    tool_trace: list[dict],
) -> str | None:
    """'Yes' to 'Shall I remind you when it's time to take it off?'."""

    if is_negative_report(message):
        return f"That's fine{_who(first_name)}."

    if not is_affirmative(message) or schedule_checkin is None:
        return None

    minutes = int(offer["minutes"])
    due = now + timedelta(minutes=minutes)
    entry = {
        "checkin_id": f"{now.date().isoformat()}#follow_on#{offer['after_occurrence_id']}",
        "due_at": due.isoformat(),
        "type": "follow_on",
        "text": offer["text"],
        "occurrence_id": offer.get("occurrence_id"),
        "item_type": "task",
    }

    try:
        await asyncio.to_thread(schedule_checkin, entry)
        ok = True
    except Exception:
        ok = False

    tool_trace.append({
        "tool": "schedule_checkin",
        "arguments": {"type": "follow_on", "due_at": entry["due_at"], "occurrence_id": entry["occurrence_id"]},
        "ok": ok,
    })

    if not ok:
        return "I couldn't set that reminder just now."

    return f"Okay{_who(first_name)}. I'll remind you in {time_words_minutes(minutes)}."


MISSED_DOSE_NOT_IN_LETTER = (
    "Your letter doesn't say what to do about a missed dose. "
    "Please ask your pharmacist or call the number on your letter."
)

# A letter sentence about a missed or forgotten dose.
_MISSED_DOSE_SENTENCE = re.compile(
    r"[^.!?\n]*\b(miss(ed)?|forget|forgot|forgotten)\b[^.!?\n]*\bdose\b[^.!?\n]*[.!?]"
    r"|[^.!?\n]*\bdose\b[^.!?\n]*\b(miss(ed)?|forget|forgot|forgotten)\b[^.!?\n]*[.!?]",
    re.IGNORECASE,
)


async def _missed_dose_advice(medicine: str | None, tool_trace: list[dict]) -> tuple[str, dict | None]:
    """
    'Should I take two?' / 'What if I missed it?': only what the letter says.

    The letter is searched; a sentence about a missed dose is quoted word
    for word. If there is none, the fixed reply sends her to the
    pharmacist. Never advises doubling or skipping.
    """

    arguments = {"query": f"missed dose {medicine or 'medicine'}"}

    try:
        result = get_structured_tool_result(
            await call_mcp_tool("search_discharge_instructions", arguments)
        )
    except Exception:
        result = None

    ok = isinstance(result, dict) and result.get("ok") is True
    tool_trace.append({"tool": "search_discharge_instructions", "arguments": arguments, "ok": ok})

    for match in collect_rag_matches("search_discharge_instructions", result) if ok else []:
        # Search the letter's own blocks (wrapped lines re-joined, headings apart).
        for block in letter_blocks(str(match.get("text") or "")):
            found = _MISSED_DOSE_SENTENCE.search(block["text"])
            if found:
                sentence = found.group(0).strip()
                return f"Your letter says: {sentence}", evidence_source(match, sentence, sentence)

    return MISSED_DOSE_NOT_IN_LETTER, None


def _who(first_name: str | None) -> str:
    return f", {first_name}" if first_name else ""


async def _missed_dose_turn(
    message: str,
    pending_checkin: dict,
    today: dict[str, list],
    now,
    first_name: str | None,
    session_id: str,
    tool_trace: list[dict],
    can_schedule: bool,
) -> tuple[str, dict | None] | None:
    """
    The reply to "Have you taken your blood thinner?" (a missed-dose check-in).

    yes / "I took it"   -> report_medication_taken for THAT dose
    no / not yet        -> nothing saved; offer one re-check in 30 minutes
    "should I take two?" -> only what the letter says
    anything else       -> None (the usual path answers)
    """

    dose = next(
        (m for m in today["medications"] if m.get("occurrence_id") == pending_checkin.get("occurrence_id")),
        None,
    )

    if dose is None:
        return None

    medicine = medicine_name(item_name(dose))

    if is_missed_dose_question(message):
        return await _missed_dose_advice(medicine, tool_trace)

    if is_negative_report(message):
        tool_trace.append(_blocked_note("report_medication_taken"))
        if pending_checkin.get("recheck") or not can_schedule:
            return f"That's okay{_who(first_name)}. Your {medicine} is still in today's plan.", None
        set_offer(session_id, {
            "kind": "recheck",
            "occurrence_id": dose["occurrence_id"],
            "medicine": medicine,
            "slot": pending_checkin.get("slot"),
        })
        return (
            f"That's okay{_who(first_name)}. Would you like me to remind you again in "
            f"{time_words_minutes(checkin_config.RECHECK_MINUTES)}?",
            None,
        )

    if is_affirmative(message) or expected_write_tool(message) == "report_medication_taken":
        if dose.get("status") == "completed":
            return f"That's already noted{_who(first_name)}. Thank you.", None
        if is_short_dose(message, dose) is not None:
            return short_dose_reply(dose), None
        if not await _write("report_medication_taken", dose, tool_trace):
            return _failed_write_reply(), None
        return _after_write(dose, True, today, now, first_name, tool_trace), None

    return None


def time_words_minutes(minutes: int) -> str:
    words = {15: "fifteen minutes", 20: "twenty minutes", 30: "30 minutes", 60: "an hour"}
    return words.get(minutes, f"{minutes} minutes")


async def _answer_recheck_offer(
    message: str,
    offer: dict,
    now,
    first_name: str | None,
    schedule_checkin: Callable[[dict], None] | None,
    tool_trace: list[dict],
) -> str | None:
    """'Yes' to 'Would you like me to remind you again in 30 minutes?'."""

    if is_negative_report(message):
        return f"That's fine{_who(first_name)}. Your {offer['medicine']} is still in today's plan."

    if not is_affirmative(message) or schedule_checkin is None:
        return None

    due = now + timedelta(minutes=checkin_config.RECHECK_MINUTES)
    entry = {
        "checkin_id": f"{now.date().isoformat()}#missed_dose#{offer['occurrence_id']}#recheck",
        "due_at": due.isoformat(),
        "type": "missed_dose",
        "text": recheck_text(first_name, offer["medicine"]),
        "occurrence_id": offer["occurrence_id"],
        "item_type": "medication",
        "slot": offer.get("slot"),
        "recheck": True,
    }

    try:
        await asyncio.to_thread(schedule_checkin, entry)
        ok = True
    except Exception:
        ok = False

    tool_trace.append({
        "tool": "schedule_checkin",
        "arguments": {"type": "missed_dose", "due_at": entry["due_at"], "occurrence_id": offer["occurrence_id"]},
        "ok": ok,
    })

    if not ok:
        return "I couldn't set that reminder just now. Please tell me when you've taken it."

    return f"Okay{_who(first_name)}. I'll check with you again in {time_words_minutes(checkin_config.RECHECK_MINUTES)}."


def _saved_this_turn(tool_trace: list[dict]) -> bool:
    """Whether a report was really written this turn."""

    return any(step["tool"] in _SCHEDULE_READ_FOR_WRITE and step.get("ok") for step in tool_trace)


def _without_repeated_prompt(
    reply: str,
    intent: Intent,
    today: dict[str, list] | None,
    now,
    session_id: str,
    saved: bool = False,
) -> str:
    """
    Never the same medicine prompt twice in a row, unless she asked for it.

    "Next is your blood thinner." is dropped from a reply when the reply before
    it gave the same prompt. It always stays when she asked what is next, and
    after a report that was saved: she has just done something, so she is told
    what comes next. Remembers what this reply prompted, for next time.
    """

    steps = build_steps(build_next_up(today["tasks"], today["medications"], now)) if today else []
    sentence = next_step_sentence(steps) if steps else None

    if not sentence or sentence not in reply:
        set_last_prompt(session_id, None)
        return reply

    ids = step_ids(steps[0])
    is_medicine = any(item.occurrence.get("medication_id") for item in steps[0])
    rest = reply.replace(sentence, "").strip()

    if is_medicine and rest and not saved and intent is not Intent.PLAN_QUESTION and get_last_prompt(session_id) == ids:
        set_last_prompt(session_id, None)
        return rest

    set_last_prompt(session_id, ids)

    return reply


def prompt_names(items: list[dict]) -> list[str]:
    """How today's unfinished items are named in a reply: 'apixaban', 'blood thinner', 'walk'."""

    names = set()

    for item in items:
        if item.get("status") == "completed":
            continue
        name = item_name(item)
        if item.get("medication_id") or item.get("dose"):
            names.add(name.lower().split(",")[0].strip())
            if everyday_name(name):
                names.add(everyday_name(name))
        else:
            names.add(short_task_name(name))

    return sorted(name for name in names if name)


async def _symptom_turn(
    message: str,
    first_name: str | None,
    tool_trace: list[dict],
) -> tuple[str, dict | None, list[dict]]:
    """
    "My head is hurting": only the letter's own warning sign, or the fixed sentence.

    Reads the plan's warning_signs, then searches the letter. Never a medicine
    or task prompt, never a write, and no model. Logs a "symptom" event with
    the matched warning sign's id, or "none": never her words.
    """

    symptom = find_symptom(message)

    try:
        plan = get_structured_tool_result(await call_mcp_tool("get_recovery_plan", {}))
    except Exception:
        plan = None

    ok = isinstance(plan, dict) and plan.get("ok") is True
    tool_trace.append({"tool": "get_recovery_plan", "arguments": {}, "ok": ok})

    warning_signs = ((plan or {}).get("data") or {}).get("warning_signs") or [] if ok else []
    sign = match_warning_sign(symptom, warning_signs)
    help_lines = help_actions(warning_signs)

    if sign is not None:
        sign_id = str(sign.get("id") or "unknown")
        log("symptom", reason=sign_id, kind="warning_sign")
        return warning_sign_reply(sign, first_name), sign_source(sign), help_lines

    # Not among the warning signs: look in the rest of the letter for the same symptom.
    arguments = {"query": message}

    try:
        found = get_structured_tool_result(await call_mcp_tool("search_discharge_instructions", arguments))
    except Exception:
        found = None

    matches = collect_rag_matches("search_discharge_instructions", found)
    tool_trace.append({"tool": "search_discharge_instructions", "arguments": arguments, "ok": bool(matches)})

    for match in matches:
        items = [sentence for item in split_letter_items(match["text"]) for sentence in letter_sentences(item)]
        sentence = match_letter_sentence(symptom, items)
        if sentence:
            log("symptom", reason="letter_passage", kind="letter")
            return letter_sentence_reply(sentence, first_name), evidence_source(match, sentence), help_lines

    log("symptom", reason="none", kind="template")

    return no_match_reply(symptom, first_name), None, help_lines


async def _food_turn(
    message: str,
    today: dict[str, list],
    first_name: str | None,
    session_id: str,
    tool_trace: list[dict],
) -> str:
    """
    "I ate pizza for breakfast": food advice only from the letter's
    diet_advice, then the medicines the letter ties to that meal.
    Nothing is written for food.
    """

    try:
        plan = get_structured_tool_result(await call_mcp_tool("get_recovery_plan", {}))
    except Exception:
        plan = None

    ok = isinstance(plan, dict) and plan.get("ok") is True
    tool_trace.append({"tool": "get_recovery_plan", "arguments": {}, "ok": ok})

    diet_advice = ((plan or {}).get("data") or {}).get("diet_advice") or [] if ok else []
    # Kept for the letter panel: the reply's quoted diet lines become its source.
    _TURN.get()["diet_advice"] = diet_advice
    kind = classify_food_message(message)

    if kind in (PLAN, NOT_YET):
        # About to eat, or not eaten yet: no judgement about food, and a
        # reminder (never "have you taken them?") for that meal's medicines.
        for meal in meals_named(message):
            doses = medicines_for_meal(meal, today["medications"])
            if doses:
                return meal_medicines_reminder(meal, doses)
        if kind == NOT_YET:
            return f"That's okay{_who(first_name)}."
        return f"Thanks for letting me know{_who(first_name)}."

    if kind != ATE:
        # A question: only the letter's own words, never a yes or no.
        return food_question_reply(message, diet_advice)

    # She ate. A meal with no food named ("I had breakfast"): nothing to say about
    # food, so go straight to the medicines for that meal.
    food_part = diet_reply(message, diet_advice, first_name) if foods_named(message) else ""

    for meal in meals_named(message):
        doses = medicines_for_meal(meal, today["medications"])
        if doses:
            set_offer(session_id, {"kind": "meal_medicines", "occurrence_ids": [d["occurrence_id"] for d in doses]})
            return f"{food_part} {meal_medicines_question(meal, doses)}".strip()

    return food_part or f"Thanks for telling me{_who(first_name)}."


async def _answer_which_medicines(
    message: str,
    offer: dict,
    today: dict[str, list],
    now,
    first_name: str | None,
    session_id: str,
    tool_trace: list[dict],
) -> str | None:
    """
    Her answer to "Have you taken them?" or "Which one did you take?".

    Saved only when it is clear which medicines and that the full dose
    was taken (app.agent.dose_answers). None when the message is not an
    answer, so the usual path handles it.
    """

    doses = [
        m for m in today["medications"]
        if m.get("occurrence_id") in offer["occurrence_ids"] and m.get("status") != "completed"
    ]

    if not doses:
        return None

    negative = is_negative_report(message)
    answer = parse_dose_answer(message, doses, carried=offer.get("stated"), negative=negative)

    if answer.kind == "none":
        tool_trace.append(_blocked_note("report_medication_taken"))
        return not_yet_reply(doses, first_name, True)

    if answer.kind == "ask":
        # Not an answer at all ("what's next?"): let the usual path reply.
        if answer.stated is None and not answer.partial and not is_affirmative(message):
            return None
        set_offer(session_id, {
            "kind": "which_medicines",
            "occurrence_ids": [d["occurrence_id"] for d in doses],
            "stated": answer.stated,
        })
        return which_one_question(doses)

    saved = []
    for dose in answer.take:
        if not await _write("report_medication_taken", dose, tool_trace):
            return _failed_write_reply()
        _mark_done(today, dose["occurrence_id"])
        saved.append(dose)

    short = [dose for dose, _ in answer.short]
    if short:
        tool_trace.append(_blocked_note("report_medication_taken", {"occurrence_id": short[0]["occurrence_id"]})
                          | {"note": "Not recorded: less than the dose in the letter."})

    still_open = [d for d in doses if d not in saved and d not in short]

    # Keep the question open for what is left, so "paracetamol, one tablet"
    # on the next turn is still read as an answer.
    remaining = [d for d in doses if d not in saved]
    if remaining and (saved or short):
        set_offer(session_id, {
            "kind": "which_medicines",
            "occurrence_ids": [d["occurrence_id"] for d in remaining],
            "stated": None,
        })

    parts = []
    if saved:
        parts.append(saved_doses_reply(saved, still_open, first_name))
        if not still_open and not short:
            # Everything asked about is done: well done, then the next step only.
            _, steps = _next_up(today, now, tool_trace)
            parts.append(next_step_sentence(steps))
    if short:
        parts.append(short_dose_reply(short[0]))

    return " ".join(parts)


def _named_items(message: str, items: list[dict]) -> list[dict]:
    """Which of these saved items she names ('the blood thinner', 'my walk')."""

    tokens = dose_tokens(message)
    named = []

    for item in items:
        if item.get("medication_id"):
            if dose_mentions(tokens, item):
                named.append(item)
        elif items_mentioned(message, [dict(item, status="pending")]):
            named.append(item)

    return named


async def _undo(items: list[dict], today: dict[str, list] | None, tool_trace: list[dict]) -> bool:
    """Change these saved items back with undo_report; True if every undo worked."""

    for item in items:
        arguments = {"occurrence_id": item["occurrence_id"]}
        try:
            result = get_structured_tool_result(await call_mcp_tool("undo_report", arguments))
        except Exception:
            result = None
        ok = isinstance(result, dict) and result.get("ok") is True
        tool_trace.append({"tool": "undo_report", "arguments": arguments, "ok": ok})
        if not ok:
            return False
        for field in ("tasks", "medications"):
            for occurrence in (today or {}).get(field, []):
                if occurrence.get("occurrence_id") == item["occurrence_id"]:
                    occurrence["status"] = "pending"

    return True


async def _correct(
    message: str,
    saved: list[dict],
    today: dict[str, list] | None,
    session_id: str,
    tool_trace: list[dict],
) -> str | None:
    """
    "No, I didn't take the blood thinner" right after a save: change back
    only that item. History is kept (an "undone" event).
    """

    if not saved or not is_correction(message):
        return None

    targets = _named_items(message, saved)

    if not targets:
        if len(saved) > 1:
            set_offer(session_id, {"kind": "undo_which", "items": saved})
            return undo_question(saved)
        targets = saved

    if not await _undo(targets, today, tool_trace):
        return "I couldn't change that back just now. Please try again in a moment."

    return undone_reply(targets)


def _remember_saves(session_id: str, tool_trace: list[dict], today: dict[str, list] | None, now=None) -> None:
    """
    What this turn saved, so a correction on the next turn can undo exactly
    that. A save also resets "and after that?" to the step just named.
    """

    saved_ids = [
        step["arguments"].get("occurrence_id")
        for step in tool_trace
        if step["tool"] in ("report_medication_taken", "report_task_completed") and step["ok"]
    ]
    items = [
        dict(occurrence)
        for field in ("tasks", "medications")
        for occurrence in (today or {}).get(field, [])
        if occurrence.get("occurrence_id") in saved_ids
    ]

    set_last_saved(session_id, items)

    if items and today is not None and now is not None:
        steps = build_steps(build_next_up(today["tasks"], today["medications"], now))
        if steps:
            set_step_pointer(session_id, 0, step_ids(steps[0]))


# Shown in Developer view when a write was held back; nothing is saved.
NOT_RECORDED_NOTE = "Not recorded: she said she has not done it yet."


def _blocked_note(tool_name: str, arguments: dict | None = None) -> dict:
    # She did not report it (a "no", or nothing clear enough to record).
    log("write_blocked", tool=tool_name, kind="write", reason="not_reported", blocked_writes=1)

    return {
        "tool": tool_name,
        "arguments": arguments or {},
        "ok": False,
        "blocked": True,
        "note": NOT_RECORDED_NOTE,
    }


def _not_yet(
    message: str,
    last_reply: str,
    denied_write: str,
    today: dict[str, list] | None,
    pending_checkin: dict | None,
    first_name: str | None,
) -> str:
    """Reply to "no, not yet": nothing recorded, the item is still in the plan."""

    is_medication = denied_write == "report_medication_taken"
    occurrences = (today or {}).get("medications" if is_medication else "tasks", [])

    still_to_do = items_mentioned(message, occurrences) or items_mentioned(last_reply, occurrences)

    if not still_to_do and pending_checkin:
        still_to_do = [
            o for o in occurrences
            if o.get("occurrence_id") == pending_checkin.get("occurrence_id")
            and o.get("status") != "completed"
        ]

    return not_yet_reply(still_to_do, first_name, is_medication)


def _reminder_ack(today: dict[str, list] | None, pending_checkin: dict) -> str:
    """The fixed reply to "thanks, I'm getting ready" while a reminder waits."""

    occurrences = (today or {}).get("tasks", []) + (today or {}).get("medications", [])
    reminded = next(
        (o for o in occurrences if o.get("occurrence_id") == pending_checkin.get("occurrence_id")),
        None,
    )
    is_medication = bool(reminded and reminded.get("medication_id")) or (
        pending_checkin.get("item_type") == "medication"
    )
    same_item = [
        o for o in occurrences
        if reminded is not None and item_id(o) == item_id(reminded)
    ]

    return reminder_ack_reply(reminded, same_item, is_medication)


async def _vague_medication(
    message: str,
    today: dict[str, list],
    now,
    pending_checkin: dict | None,
    first_name: str | None,
    session_id: str,
    tool_trace: list[dict],
) -> str:
    """'I took my tablets': record the one medicine due, or ask which."""

    resolution = resolve_vague_medication(today["medications"], now, pending_checkin)

    if resolution.action == "ask":
        stated = stated_count(message)
        set_offer(session_id, {
            "kind": "which_medicines",
            "occurrence_ids": [d["occurrence_id"] for d in resolution.choices],
            "stated": stated,
        })
        # She gave a count ("one tablet"): ask which one, not "which, or both?".
        return which_one_question(resolution.choices) if stated else ask_which_medicine(resolution.choices)

    if resolution.action == "record":
        if is_short_dose(message, resolution.occurrence) is not None:
            return short_dose_reply(resolution.occurrence)
        if not await _write("report_medication_taken", resolution.occurrence, tool_trace):
            return _failed_write_reply()

        return _after_write(resolution.occurrence, True, today, now, first_name, tool_trace)

    return AMBIGUOUS_MEDICATION_REPLY


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
    **options: Any,
) -> dict[str, Any]:
    """
    Run one conversational turn (see _chat_turn) and log one agent_turn line.

    The line holds counts and timings only: which path answered (code or
    model), the model, tool calls, tokens and total time.
    """

    timer = Timer()
    session = hash_session(session_id)

    try:
        result = await _chat_turn(message, session_id, patient_context, **options)
    except Exception as exc:
        log("agent_turn", level="error", error=exc, session_id_hash=session, status="error",
            ms=timer.ms, chat_ms=timer.ms)
        raise

    # Set only when the model was called; a code path answers without it.
    stats = _TURN.get().get("stats") or {}
    tool_calls = len(result["tool_trace"])
    status = "ok" if result.get("completed") else "tool_round_limit"

    log(
        "agent_turn",
        session_id_hash=session,
        kind="model" if stats else "code",
        model=stats.get("model"),
        tool_calls=tool_calls,
        tokens_in=stats.get("tokens_in"),
        tokens_out=stats.get("tokens_out"),
        status=status,
        ms=timer.ms,
        chat_ms=timer.ms,
    )

    return result


async def _chat_turn(
    message: str,
    session_id: str,
    patient_context: str | None = None,
    *,
    pending_checkin: dict | None = None,
    first_name: str | None = None,
    timezone: str = "Europe/London",
    schedule_checkin: Callable[[dict], None] | None = None,
) -> dict[str, Any]:
    """
    Run one conversational turn.

    pending_checkin, first_name and timezone come from the caller's
    server-side RecoveryState, never from the patient's message.
    schedule_checkin(entry), if given, saves a scheduled check-in for
    this patient ("remind me again in 30 minutes").

    Returns:
        {
            "response": patient-facing reply,
            "tool_trace": MCP tools Claude called, in order,
            "source": RAG evidence for paperwork answers, or None,
            "completed": False if the tool-round limit was hit,
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

    history = get_history(session_id)
    last_reply = next(
        (item["content"] for item in reversed(history) if item["role"] == "assistant"),
        "",
    )

    # The write guard reads this turn's message and the question she is
    # answering from here (see _execute_tool).
    _TURN.set({
        "message": cleaned_message, "question": None, "today": None, "blocked": [],
        "session_id": session_id, "first_name": first_name, "now": None,
    })

    # "No, I haven't taken it" must never become a write. Anything
    # negative blocks every report_* tool for this turn.
    negative = is_negative_report(cleaned_message)
    required_write = None if negative else expected_write_tool(cleaned_message)

    # The facts for this turn: the patient's local time (shared
    # clock, so DEMO_FIXED_NOW applies) and today's occurrences.
    now = get_patient_datetime(timezone or "Europe/London")
    today = await _load_today(tool_trace)
    _TURN.get()["today"] = today
    _TURN.get()["now"] = now

    # Schedule reads (get_today_tasks / get_medications) that
    # returned no items today. With nothing scheduled no write
    # is possible, so the write check must not push the model
    # to apologise or guess.
    empty_schedules: set[str] = set()

    if today is not None:
        empty_schedules.update(
            tool_name for tool_name, field in _FACT_READS if today[field] == []
        )

    resolved_reply = None
    resolved_source = None
    # Filled by a completion: the letter source and any follow-on offer.
    extras: dict = {}

    # An offer from the previous turn is answered now or dropped, and
    # what the previous turn saved can be corrected now.
    offer = pop_offer(session_id)
    last_saved = pop_last_saved(session_id)

    # Intent first, every turn. The waiting question is the offer from the last
    # reply, or a check-in she has not answered yet.
    intent = classify_intent(cleaned_message, offer or pending_checkin, today)
    _TURN.get()["intent"] = intent

    if intent is Intent.SYMPTOM:
        # A symptom always wins: no pending question, no next step, no write.
        symptom_reply, symptom_source, help_lines = await _symptom_turn(cleaned_message, first_name, tool_trace)
        set_last_prompt(session_id, None)
        add_message(session_id, "user", cleaned_message)
        add_message(session_id, "assistant", symptom_reply)

        return {
            "response": symptom_reply,
            "tool_trace": tool_trace,
            "source": symptom_source,
            "completed": True,
            # Shown as the "Get help" card on the Today screen.
            "help": {"actions": help_lines},
        }

    # A waiting question lasts one turn, and only an answer uses it.
    if intent is not Intent.ANSWER:
        offer = None
        if intent is not Intent.REPORT:
            # A report may still be about the reminded item ("I've done it").
            pending_checkin = None

    # Nothing is written unless she reported something or answered a question.
    writes_allowed = intent in (Intent.REPORT, Intent.ANSWER)
    # The question she is answering: a medicine question, or a waiting check-in.
    _TURN.get()["question"] = offer if offer and "occurrence_ids" in offer else pending_checkin
    missed_dose_pending = bool(pending_checkin) and pending_checkin.get("type") == "missed_dose"

    resolved_reply = await _correct(cleaned_message, last_saved, today, session_id, tool_trace)

    if resolved_reply is not None:
        pass

    elif offer and offer.get("kind") == "undo_which":
        targets = _named_items(cleaned_message, offer["items"])
        if targets:
            resolved_reply = (
                undone_reply(targets) if await _undo(targets, today, tool_trace)
                else "I couldn't change that back just now. Please try again in a moment."
            )

    elif offer and offer.get("kind") == "recheck":
        resolved_reply = await _answer_recheck_offer(
            cleaned_message, offer, now, first_name, schedule_checkin, tool_trace,
        )
    elif offer and offer.get("kind") == "follow_on":
        resolved_reply = await _answer_follow_on_offer(
            cleaned_message, offer, now, first_name, schedule_checkin, tool_trace,
        )
    elif offer and offer.get("kind") in ("meal_medicines", "which_medicines") and today is not None:
        resolved_reply = await _answer_which_medicines(
            cleaned_message, offer, today, now, first_name, session_id, tool_trace,
        )

    if resolved_reply is not None:
        pass

    elif missed_dose_pending and today is not None:
        # "Have you taken your blood thinner?" — answered in code.
        answer = await _missed_dose_turn(
            cleaned_message, pending_checkin, today, now, first_name,
            session_id, tool_trace, can_schedule=schedule_checkin is not None,
        )
        if answer is not None:
            resolved_reply, resolved_source = answer

    if resolved_reply is not None:
        pass

    elif is_missed_dose_question(cleaned_message):
        # "What if I missed my blood thinner?" with no check-in waiting.
        named = items_mentioned(cleaned_message, (today or {}).get("medications", []))
        medicine = medicine_name(item_name(named[0])) if named else None
        resolved_reply, resolved_source = await _missed_dose_advice(medicine, tool_trace)

    elif (
        today is not None
        and is_food_message(cleaned_message, [str(item_name(m)) for m in today["medications"]])
        and (
            # "What's left? I'm about to have breakfast" is about the day;
            # "what else can I eat?" is about food.
            re.search(r"\b(eat|eating|drink|drinking|food|diet)\b", cleaned_message.lower())
            or not (is_next_up_question(cleaned_message) or asks_whats_left_today(cleaned_message))
        )
    ):
        # "I ate pizza for breakfast": never judged except by the letter.
        resolved_reply = await _food_turn(cleaned_message, today, first_name, session_id, tool_trace)
        # Open the letter at its eating and drinking lines, as for any letter answer.
        resolved_source = diet_source(resolved_reply, _TURN.get().get("diet_advice") or [])

    elif (
        pending_checkin
        and "?" not in cleaned_message
        and expected_write_tool(cleaned_message) is None
        and (is_acknowledgement(cleaned_message) or negative)
    ):
        # "Thanks, I'm just getting ready" in reply to a reminder:
        # acknowledge once, record nothing, do not repeat the reminder.
        resolved_reply = _reminder_ack(today, pending_checkin)

    elif negative:
        # What she says she has not done: from her words, or from
        # AfterWard's last question ("Have you taken ...?" "Not yet").
        denied_write = (
            expected_write_tool(cleaned_message.replace("?", ""))
            or asked_about_completion(last_reply)
        )

        if denied_write and "?" not in cleaned_message:
            tool_trace.append(_blocked_note(denied_write))
            resolved_reply = _not_yet(
                cleaned_message, last_reply, denied_write, today, pending_checkin, first_name,
            )

    elif today is not None and required_write is None and asks_after_that(cleaned_message):
        # "And after that?": one step on from the step last mentioned.
        _, steps = _next_up(today, now, tool_trace)
        pointer = get_step_pointer(session_id)
        if pointer is None:
            resolved_reply = whats_next_reply(first_name, steps)
            if steps:
                set_step_pointer(session_id, 0, step_ids(steps[0]))
        else:
            # Find the step last mentioned (the day may have moved on), then go one on.
            index = next(
                (i for i, step in enumerate(steps) if step_ids(step) == pointer["ids"]),
                pointer["index"],
            ) + 1
            resolved_reply = after_that_sentence(steps, index)
            if index < len(steps):
                set_step_pointer(session_id, index, step_ids(steps[index]))

    elif today is not None and required_write is None and asks_whats_left_today(cleaned_message):
        # "What's left today?": a short summary by part of the day.
        items, _ = _next_up(today, now, tool_trace)
        resolved_reply = day_summary(items, first_name)

    elif today is not None and required_write is None and is_next_up_question(cleaned_message):
        # "What's next?": only the next step.
        _, steps = _next_up(today, now, tool_trace)
        resolved_reply = whats_next_reply(first_name, steps)
        if steps:
            set_step_pointer(session_id, 0, step_ids(steps[0]))

    elif (
        today is not None and required_write and writes_allowed
        and (report_parts := _compound_parts(cleaned_message, today))
        and (compound_reply := await _compound_report(
            report_parts, today, now, pending_checkin, first_name, tool_trace, extras,
        )) is not None
    ):
        # "I did my walk and I took my paracetamol": both are recorded, both are named.
        resolved_reply = compound_reply
        resolved_source = extras.get("source") or resolved_source

    elif is_ambiguous_medication_write(cleaned_message) or (
        required_write == "report_medication_taken"
        and today is not None
        and count_without_name(cleaned_message, today["medications"])
    ):
        # "I took my tablets" / "I've taken one tablet": never let the model
        # guess which medicine; ask in code, and remember any count she gave.
        # Never let the model guess which medicine "my tablets" means.
        resolved_reply = (
            await _vague_medication(cleaned_message, today, now, pending_checkin, first_name, session_id, tool_trace)
            if today is not None
            else AMBIGUOUS_MEDICATION_REPLY
        )

    # "I'm back from my walk": choose the occurrence in code and
    # write it, rather than letting the model ask which walk.
    elif required_write and today is not None:
        resolved_reply = await _resolve_completion(
            cleaned_message,
            required_write,
            today,
            now,
            pending_checkin,
            first_name,
            tool_trace,
            extras,
        )
        resolved_source = extras.get("source") or resolved_source

    if extras.get("offer"):
        set_offer(session_id, extras["offer"])

    if resolved_reply is not None:
        resolved_reply = _without_repeated_prompt(
            resolved_reply, intent, today, now, session_id, saved=_saved_this_turn(tool_trace),
        )
        _remember_saves(session_id, tool_trace, today, now)
        add_message(session_id, "user", cleaned_message)
        add_message(session_id, "assistant", resolved_reply)

        return {
            "response": resolved_reply,
            "tool_trace": tool_trace,
            "source": resolved_source,
            "completed": True,
        }

    tool_config = await build_bedrock_tool_config()

    messages = build_bedrock_messages(
        history,
        cleaned_message,
    )

    # Next steps are offered only after a report or a question about the plan.
    quiet = intent is Intent.OTHER

    facts = (
        _describe_facts(today, now, pending_checkin, first_name, quiet=quiet)
        if today is not None
        else None
    )

    system = _build_system_prompt(patient_context, facts)
    model_id = get_agent_model_id()

    response_text = ""

    write_nudged = False

    grounding_nudged = False
    letter_search_nudged = False

    # False only when the tool-round limit stopped the turn early.
    completed = True

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

        usage = response.get("usage") or {}
        stats = _TURN.get().setdefault("stats", {"model": model_id, "tokens_in": 0, "tokens_out": 0})
        stats["tokens_in"] += int(usage.get("inputTokens") or 0)
        stats["tokens_out"] += int(usage.get("outputTokens") or 0)

        assistant_message = response["output"]["message"]
        messages.append(assistant_message)

        # Only the final message is spoken. Text written alongside a
        # tool call ("let me record those...") is a half-thought.
        if response["stopReason"] != "tool_use":

            response_text = _extract_text(assistant_message)

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
                # A refused write means "ask her", never "try again".
                and not _TURN.get().get("blocked")
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

            # Permission answers need a fresh letter search so the patient
            # can see the supporting passage, even if the model read the plan.
            searched_letter = any(
                item["tool"] == "search_discharge_instructions"
                for item in tool_trace
            )
            if is_permission_question(cleaned_message) and not searched_letter and not letter_search_nudged:
                letter_search_nudged = True
                response_text = ""
                messages.append({
                    "role": "user",
                    "content": [{"text": (
                        "[System check] This question asks whether an activity is allowed. "
                        "Call search_discharge_instructions with the patient's question "
                        "before answering. Use the returned letter wording and include "
                        "its evidence tag. If the letter does not answer it, say so; "
                        "do not guess permission."
                    )}],
                })
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

            if tool_name in _SCHEDULE_READ_FOR_WRITE and (
                not writes_allowed or (negative and tool_name == "report_task_completed")
            ):
                # She did not report it, or said she has not done it: never write.
                # (A medicine she did report is still checked in _execute_tool.)
                tool_trace.append(_blocked_note(tool_name, arguments))
                tool_results.append(
                    {
                        "toolResult": {
                            "toolUseId": tool_use["toolUseId"],
                            "content": [
                                {
                                    "json": {
                                        "ok": False,
                                        "error": {
                                            "code": "NOT_RECORDED",
                                            "message": NOT_RECORDED_NOTE,
                                            "next_step": (
                                                "Do not record anything. Say kindly "
                                                "that it is still in today's plan."
                                            ),
                                        },
                                    }
                                }
                            ],
                            "status": "error",
                        }
                    }
                )
                continue

            structured_result, ok, _ = await _execute_tool(tool_name, arguments, tool_trace)
            is_error = not ok

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
        completed = False
        response_text = (
            "Sorry, I couldn't finish that. "
            "Please try asking again."
        )

    # A medicine write was refused and none was saved: the code replies,
    # never the model ("I've noted ..." would be untrue).
    if _TURN.get().get("blocked") and not any(
        step["tool"] == "report_medication_taken" and step["ok"] for step in tool_trace
    ):
        response_text = _refused_write_reply() or response_text

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

    # The model recorded a completion (she named which one): reply
    # the same way as the code-resolved path, with what is next.
    written = [
        item for item in tool_trace
        if required_write and item["tool"] == required_write and item["ok"]
    ]

    if written and today is not None:
        for item in written:
            _mark_done(today, str(item["arguments"].get("occurrence_id")))
        occurrence = next(
            (
                o for field in ("tasks", "medications") for o in today[field]
                if o.get("occurrence_id") == written[-1]["arguments"].get("occurrence_id")
            ),
            None,
        )
        if occurrence is not None:
            response_text = _after_write(
                occurrence,
                required_write == "report_medication_taken",
                today,
                now,
                first_name,
                tool_trace,
                extras,
            )
            if extras.get("offer"):
                set_offer(session_id, extras["offer"])

    # The evidence tag is for the source only; never speak it.
    response_text, cited_chunk_id, cited_line = split_citation(
        response_text
    )

    # Voice-first: no reply may point at a screen, and none opens
    # with "You're right" as if the patient had corrected it.
    response_text = tidy_reply(
        remove_hollow_openers(remove_screen_references(response_text))
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

    # A follow-on reply ("put an ice pack on your knee") quotes the letter.
    if extras.get("source"):
        source = extras["source"]

    if quiet and today is not None:
        # In code, not only in the prompt: she did not ask, so no prompt about
        # a medicine or task survives in the reply.
        response_text = remove_unasked_prompts(
            response_text, cleaned_message, prompt_names(today["tasks"] + today["medications"]),
        )

    response_text = _without_repeated_prompt(
        response_text, intent, today, now, session_id, saved=_saved_this_turn(tool_trace),
    )
    _remember_saves(session_id, tool_trace, today, now)

    # Only plain text goes into session history; tool calls
    # are re-fetched from MCP on every turn.
    add_message(session_id, "user", cleaned_message)
    add_message(session_id, "assistant", response_text)

    return {
        "response": response_text,
        "tool_trace": tool_trace,
        "source": source,
        "completed": completed,
    }
