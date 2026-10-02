import json
import boto3

from models.recovery_model import (
    RecoveryPlan,
    Medication,
    Task,
    Appointment,
    Source,
)


bedrock = boto3.client(
    "bedrock-runtime",
    region_name="eu-west-2"
)

MODEL_ID = "global.amazon.nova-2-lite-v1:0"


def extract_recovery_information(
    pages,
    patient_id,
    document_id,
    source_type="unknown"
) -> RecoveryPlan:

    document_text = "\n\n".join(
        f"PAGE {page['page']}:\n{page['text']}"
        for page in pages
    )

    prompt = f"""
You are extracting structured information from a hospital discharge document.

Extract ONLY information explicitly stated in the document.

Do not diagnose.
Do not invent information.
Do not infer missing medication doses or schedules.

If any medical information is unclear or potentially ambiguous because of handwriting quality, mark that item as needing confirmation.

Never guess an unclear medication name, dose, frequency, date, or instruction.

IMPORTANT HANDWRITING RULES:

- Do not guess unclear handwriting.
- Do not invent medication names, doses, frequencies, dates, or instructions.
- If a piece of information cannot be read reliably, represent it as [UNREADABLE].
- Preserve the wording from the source document as closely as possible.
- Every extracted medical item must include its page number and evidence from the source.
- If an item contains [UNREADABLE] or is otherwise ambiguous, mark needs_confirmation as true.
- If the information is clearly readable, mark needs_confirmation as false.

Return ONLY valid JSON.
Include needs_confirmation as a JSON boolean on every extracted medical item.
Use true for unclear or ambiguous information, including any [UNREADABLE] value; otherwise use false.

Use exactly this structure:

{{
  "discharge_date": null,
  "medications": [],
  "tasks": [],
  "appointments": [],
  "restrictions": [],
  "monitoring": [],
  "warning_signs": []
}}

For medications use:
{{
  "name": "",
  "dose": null,
  "frequency": null,
  "duration": null,
  "instructions": null,
  "page": 1,
  "evidence": "",
  "needs_confirmation": false
}}

For tasks use:
{{
  "description": "",
  "frequency": null,
  "page": 1,
  "evidence": "",
  "needs_confirmation": false
}}

For appointments use:
{{
  "type": "",
  "date": null,
  "time": null,
  "page": 1,
  "evidence": "",
  "needs_confirmation": false
}}

For restrictions, monitoring and warning_signs,
return objects containing the relevant text plus:
"page", "evidence", and "needs_confirmation".

DOCUMENT:

{document_text}
"""

    response = bedrock.converse(
        modelId=MODEL_ID,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "text": prompt
                    }
                ]
            }
        ],
        inferenceConfig={
            "maxTokens": 4000,
            "temperature": 0
        }
    )

    response_text = response["output"]["message"]["content"][0]["text"]

    print("\n===== RAW BEDROCK EXTRACTION =====\n")
    print(response_text)

    # Remove Markdown code fences if the model returned them
    response_text = response_text.strip()

    if response_text.startswith("```json"):
       response_text = response_text[len("```json"):].strip()

    if response_text.startswith("```"):
       response_text = response_text[len("```"):].strip()

    if response_text.endswith("```"):
       response_text = response_text[:-3].strip()

    data = json.loads(response_text)

    medications = []

    for index, item in enumerate(data.get("medications", []), start=1):

        source = Source(
            document_id=document_id,
            page=item["page"],
            evidence=item["evidence"],
            source_type=source_type
        )

        medications.append(
            Medication(
                medication_id=f"med_{index:03d}",
                name=item["name"],
                dose=item.get("dose"),
                frequency=item.get("frequency"),
                duration=item.get("duration"),
                instructions=item.get("instructions"),
                source=source,
                needs_confirmation=item.get("needs_confirmation", False)
            )
        )

    tasks = []

    for index, item in enumerate(data.get("tasks", []), start=1):

        source = Source(
            document_id=document_id,
            page=item["page"],
            evidence=item["evidence"],
            source_type=source_type
        )

        tasks.append(
            Task(
                task_id=f"task_{index:03d}",
                description=item["description"],
                frequency=item.get("frequency"),
                source=source,
                needs_confirmation=item.get("needs_confirmation", False)
            )
        )

    appointments = []

    for index, item in enumerate(data.get("appointments", []), start=1):

        source = Source(
            document_id=document_id,
            page=item["page"],
            evidence=item["evidence"],
            source_type=source_type
        )

        appointments.append(
            Appointment(
                appointment_id=f"appt_{index:03d}",
                type=item["type"],
                date=item.get("date"),
                time=item.get("time"),
                source=source,
                needs_confirmation=item.get("needs_confirmation", False)
            )
        )

    return RecoveryPlan(
        patient_id=patient_id,
        recovery_status="active",
        discharge_date=data.get("discharge_date"),
        medications=medications,
        tasks=tasks,
        appointments=appointments,
        restrictions=data.get("restrictions", []),
        monitoring=data.get("monitoring", []),
        warning_signs=data.get("warning_signs", [])
    )
