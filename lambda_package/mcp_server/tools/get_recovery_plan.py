from mcp_server.services.dynamodb_service import recovery_table


def get_recovery_plan(patient_id: str) -> dict:
    """
    Get the patient's current post-discharge recovery plan.
    """

    response = recovery_table.get_item(
        Key={
            "patient_id": patient_id
        }
    )

    item = response.get("Item")

    if not item:
        return {
            "success": False,
            "error": f"No recovery plan found for patient {patient_id}"
        }

    return {
        "success": True,
        "patient_id": patient_id,
        "recovery_plan": item
    }
