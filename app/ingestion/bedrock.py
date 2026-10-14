"""Send discharge text to Bedrock and return structured fields using the extraction schema."""

import boto3
from app import config
from discharge_letter_check.schema import load_schema
from jsonschema import validate
from jsonschema.exceptions import ValidationError

from app.observability.log import service_log


log = service_log("document_lambda")

def load_extraction_schema() -> dict:
    """Load a fresh dictionary from the package's canonical extraction schema."""
    return load_schema()


EXTRACTION_SCHEMA = load_extraction_schema()


PROMPT_CONSTRAINT = """You extract structured recovery information from hospital
discharge documents.

Follow these rules strictly:

1. Use only information explicitly present in the document.
2. Never guess or infer missing clinical information.
3. Distinguish medication strength from dose.
   Example:
   "Amoxicillin 500 mg - take 1 tablet"
   strength = "500 mg"
   dose = "1 tablet"
4. Do not convert vague timing words into invented clock times.
   For example:
   "in the morning"
   must NOT become "08:00".
5. Preserve wording in duration_text, instructions,
   thresholds, restrictions and source snippets.
6. For as-needed medication:
   set as_needed=true only when explicitly stated.
7. For appointments:
   preserve conflicting dates rather than silently selecting one.
8. Warning signs must preserve both:
   - what the warning is
   - what action the document tells the patient to take
9. Do not invent document_id.
   document_id is added later by the Afterward pipeline.
10. Every extracted item must include source evidence using
    text from the original document.
11. If information is not present, use null, false, or an
    empty list as required by the schema.
12. diet_advice: one item per diet, food or drink line in the
    letter (for example under a DIET heading), with text copied
    word for word. kind = "avoid" when the line tells the patient
    not to eat or drink something (for example "Do not drink
    alcohol ..."); kind = "advice" for every other diet line.
    Never add diet advice the letter does not give, and never
    reword a line.
13. tasks.follow_on: only when the letter says to do a task for
    a stated time straight after another task, e.g. "Ice pack on
    the knee for 20 minutes after each set of exercises." Put it
    on the ice-pack task: after_task = the letter's words for the
    earlier task ("each set of exercises"), duration_minutes = 20,
    source.snippet = the sentence word for word. Otherwise null.

IMPORTANT MEDICATION RULE:
Strength and dose are different fields.
- strength describes the strength/concentration written for the medicine,
  such as "500 mg" or "0.1%".
- dose describes the stated amount the patient takes each time,
  such as "1 tablet", "2 capsules", "5 mL", or "1 drop".
- Do NOT copy strength into dose merely because no separate dose is stated.

Source: "Amoxicillin 500 mg, three times daily"
Return: strength = "500 mg", dose = null.

Source: "Amoxicillin 500 mg, take 1 tablet three times daily"
Return: strength = "500 mg", dose = "1 tablet".

Never invent dose. Never infer tablet count from strength.
Preserve null when dose is not actually stated.
Do not add medication.clock_times: the schema defines clock_times only for tasks.
Use time_of_day only for time-of-day words explicitly written in the document.
Do not infer "bedtime" or another label from a clock time such as "20:00".
Preserve explicit medication clock times and maximum daily amount wording in
instructions when the schema has no dedicated field for them. For example,
"Maximum 4 g in 24 hours" belongs in instructions; max_per_day is the stated
number of administrations, not the mass in grams. Do not invent a limit.

APPOINTMENT DATE CONFLICTS:
Only populate conflicting_dates when the document genuinely gives two or more
incompatible dates for the SAME appointment. Preserve a primary date and the
actual alternatives without silently resolving the conflict.
Do NOT treat "by 25 September", "within 7 days", "to be arranged in 6 weeks",
or other deadlines or relative timing phrases as conflicting_dates unless there
is actually another incompatible appointment date for the same appointment.
If there is no real date conflict, conflicting_dates = [].

SOURCE EVIDENCE AND COMPLETENESS:
Use the supplied [Page N] labels for source.page; never invent a page number.
Preserve short verbatim source snippets and any uncertainty markers.
Preserve urgent escalation wording in warning text and action.
Return all eight top-level sections: discharge_date, medications, tasks,
appointments, restrictions, monitoring, warning_signs and diet_advice,
even when empty.
Follow the canonical schema exactly; do not add fields it does not define.
"""


_client = None
def _bedrock():
    global _client
    if _client is None:
        _client = boto3.client("bedrock-runtime", region_name=config.REGION)
    return _client

def _field_names(exc: ValidationError) -> str:
    """Unexpected or missing FIELD names (from the schema), never their values."""

    instance = exc.instance if isinstance(exc.instance, dict) else {}

    if exc.validator == "additionalProperties":
        allowed = set((exc.schema or {}).get("properties", {}))
        names = sorted(str(key) for key in instance if key not in allowed)
        return f": unexpected {', '.join(names)}" if names else ""

    if exc.validator == "required":
        names = [str(key) for key in exc.validator_value if key not in instance]
        return f": missing {', '.join(names)}" if names else ""

    return ""


def invoke_extraction_model(document_text: str) -> dict:
    """Turn discharge text into schema-valid structured data.
    Returns a dict matching EXTRACTION_SCHEMA. Raises on failure. Writes nothing."""
    if not document_text or not document_text.strip():
        raise ValueError("document_text is empty")

    model_id = config.get_extraction_model_id()

    tool = {"toolSpec": {
        "name": "record_recovery_extraction",
        "description": "Record structured information read from a discharge document.",
        "inputSchema": {"json": EXTRACTION_SCHEMA},
    }}
    resp = _bedrock().converse(
        modelId=model_id,
        system=[{"text": PROMPT_CONSTRAINT}],
        messages=[{"role": "user", "content": [
            {"text": "Extract the recovery information from this discharge document:\n\n" + document_text}
        ]}],
        toolConfig={"tools": [tool],
                    "toolChoice": {"tool": {"name": "record_recovery_extraction"}}},
        inferenceConfig={"maxTokens": 5000, "temperature": 0},
    )
    # Why the model stopped and how many tokens it used (a truncated answer shows as max_tokens).
    stop_reason = resp.get("stopReason")
    usage = resp.get("usage") or {}
    log("extraction_model", model=model_id, reason=stop_reason,
        tokens_in=usage.get("inputTokens"), tokens_out=usage.get("outputTokens"))
    if stop_reason == "max_tokens":
        raise RuntimeError(
            "Bedrock extraction was truncated because the output token limit was reached."
        )
    for block in resp["output"]["message"]["content"]:
        if "toolUse" in block:
            extracted = block["toolUse"]["input"]
            try:
                validate(instance=extracted, schema=EXTRACTION_SCHEMA)
            except ValidationError as exc:
                # Where it failed and which rule, never the value: the value
                # is letter text, and this message can reach the logs.
                where = "/".join(str(part) for part in exc.absolute_path) or "(root)"
                raise ValueError(
                    "Bedrock returned extraction data that does not match the discharge schema "
                    f"at {where} ({exc.validator}{_field_names(exc)})"
                ) from None
            return extracted
    raise RuntimeError("Model did not return structured tool output")
