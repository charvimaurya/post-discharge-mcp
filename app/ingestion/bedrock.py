import boto3
from app import config

SOURCE_SCHEMA = {
    "type": "object",
    "properties": {
        "page": {"type": ["integer", "null"]},
        "snippet": {"type": ["string", "null"]},
    },
    "required": ["page", "snippet"],
}

# The exact shape every extraction must return.
EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "discharge_date": {"type": ["string", "null"],
            "description": "Discharge date exactly as written, or null if not stated."},
        "medications": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"},
            "dose": {"type": ["string", "null"]},
            "frequency": {"type": ["string", "null"]},
            "duration": {"type": ["string", "null"]},
            "notes": {"type": ["string", "null"]},
        }, "required": ["name"]}},
        "tasks": {"type": "array", "items": {"type": "object", "properties": {
            "description": {"type": "string"},
            "timing": {"type": ["string", "null"],
                "description": "When or how often to do this task, e.g. 'every morning', 'twice daily', 'for 7 days'. Extract this into the field even if it also appears in the description. Null only if the document gives no timing."},
        }, "required": ["description"]}},
        "appointments": {"type": "array", "items": {"type": "object", "properties": {
            "with": {"type": ["string", "null"]},
            "date": {"type": ["string", "null"]},
            "time": {"type": ["string", "null"]},
            "location": {"type": ["string", "null"]},
            "status": {"type": ["string", "null"],
                "description": "booked | to_arrange | null. 'booked' if the document states it is already arranged. 'to_arrange' if the appointment still needs to be arranged, whether by the patient or the clinic as the document indicates. null if arrangement status is not indicated."},
            "notes": {"type": ["string", "null"],
                "description": "Any extra context about the appointment stated in the document, e.g. its purpose or 'letter to follow'. Null if none."},
        }}},
        "restrictions": {"type": "array", "items": {
            "type": "object", "properties": {"text": {"type": "string"}},
            "required": ["text"],
        }},
        "monitoring": {"type": "array", "items": {"type": "object", "properties": {
            "what": {"type": "string"},
            "how_often": {"type": ["string", "null"]},
            "threshold": {"type": ["string", "null"],
                "description": "The value or condition that means this reading is a concern, e.g. 'above 38.5 C', 'gain over 2 kg in 3 days'. Capture it here even if the same condition also appears in warning_signs. Null if the document states no threshold."},
        }, "required": ["what"]}},
        "warning_signs": {"type": "array", "items": {
            "type": "object", "properties": {"text": {"type": "string"}},
            "required": ["text"],
        }},
    },
    "required": ["discharge_date", "medications", "tasks", "appointments",
                 "restrictions", "monitoring", "warning_signs"],
}

for category in ("medications", "tasks", "appointments", "monitoring", "restrictions", "warning_signs"):
    item_schema = EXTRACTION_SCHEMA["properties"][category]["items"]
    item_schema["properties"]["source"] = SOURCE_SCHEMA
    item_schema.setdefault("required", []).append("source")


PROMPT_CONSTRAINT = (
    "You extract structured recovery information from a hospital discharge document. "
    "Use ONLY information explicitly present in the document. "
    "Never infer or invent a missing dose, frequency, appointment date, monitoring "
    "threshold, or restriction. If a field is not stated, leave it null or an empty list. "
    "Preserve the original intent and wording of urgent warning or escalation instructions. "
    "Do not add advice that is not in the document. "
    "For appointments, 'location' is a physical place only (hospital, clinic, address). "
    "If the document says the patient must arrange or book the appointment, do NOT put that "
    "in location; set status to 'to_arrange'. If it says the appointment is already booked, "
    "set status to 'booked'. Leave location null when no physical place is given. "
    "For every extracted medication, task, appointment, monitoring instruction, "
    "restriction, and warning sign, include source.page and source.snippet. "
    "Use the supplied [Page N] labels to identify the page; do not guess page numbers. "
    "Provide a short verbatim supporting snippet from the supplied document text. "
    "Do not invent source evidence. If a page or snippet cannot be identified "
    "confidently, set that field to null. Preserve uncertainty markers in snippets. "
    "For restrictions and warning signs, put the complete instruction, including "
    "any escalation action, in text. "
)

_client = None
def _bedrock():
    global _client
    if _client is None:
        _client = boto3.client("bedrock-runtime", region_name=config.REGION)
    return _client

def invoke_extraction_model(document_text: str) -> dict:
    """Turn discharge text into schema-valid structured data.
    Returns a dict matching EXTRACTION_SCHEMA. Raises on failure. Writes nothing."""
    if not document_text or not document_text.strip():
        raise ValueError("document_text is empty")

    model_id = config.get_extraction_model_id()

    tool = {"toolSpec": {
        "name": "record_recovery_extraction",
        "description": "Record the structured recovery information extracted from the document.",
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
        inferenceConfig={"maxTokens": 1200, "temperature": 0},
    )
    for block in resp["output"]["message"]["content"]:
        if "toolUse" in block:
            return block["toolUse"]["input"]
    raise RuntimeError("Model did not return structured tool output")
