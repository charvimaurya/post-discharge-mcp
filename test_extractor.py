from app.ingestion.pdf_processor import extract_text
from app.ingestion.extractor import extract_recovery_information


pages = extract_text("test_data/discharge.pdf")

recovery_plan = extract_recovery_information(
    pages=pages,
    patient_id="demo_patient_001",
    document_id="doc_001"
)

print("\n===== RECOVERY PLAN =====\n")

print("Patient:", recovery_plan.patient_id)
print("Discharge date:", recovery_plan.discharge_date)

print("\nMEDICATIONS:")
for medication in recovery_plan.medications:
    print(medication)

print("\nTASKS:")
for task in recovery_plan.tasks:
    print(task)

print("\nAPPOINTMENTS:")
for appointment in recovery_plan.appointments:
    print(appointment)

print("\nRESTRICTIONS:")
print(recovery_plan.restrictions)

print("\nMONITORING:")
print(recovery_plan.monitoring)

print("\nWARNING SIGNS:")
print(recovery_plan.warning_signs)
