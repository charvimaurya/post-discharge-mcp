"""Do not turn an explicitly withdrawn medicine back into a pending dose."""


def medication_withdrawn(medication: dict) -> bool:
    status = str(medication.get("status") or "").strip().lower()
    return (
        status in {"stopped", "discontinued", "cancelled", "canceled", "inactive"}
        or medication.get("active") is False
        or medication.get("stopped") is True
        or bool(medication.get("stopped_at"))
    )
