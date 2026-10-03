"""
End-to-end test for the Afterward ingestion pipeline.

This tests:

local PDF
    ↓
S3
    ↓
SQS
    ↓
Lambda
    ↓
Bedrock
    ↓
normalization
    ↓
validation
    ↓
DynamoDB

The test succeeds only when DynamoDB contains the exact
document_id uploaded by this script and ingestion_status
is "ready".
"""

import time
import sys
from pathlib import Path
from uuid import uuid4

# Direct script execution puts this script folder on sys.path; add the project packages.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.aws.s3_service import (
    upload_document,
)

from app.database.recovery_state import (
    get_recovery_state,
)


# ---------------------------------------------------------
# TEST CONFIG
# ---------------------------------------------------------

PATIENT_ID = "demo_patient_001"

# Change this if your clean synthetic PDF lives elsewhere.
FILE_PATH = str(PROJECT_ROOT / "test_data" / "doc_001.pdf")

# Maximum amount of time we'll wait for:
#
# S3
# → SQS
# → Lambda
# → Bedrock
# → DynamoDB
#
MAX_WAIT_SECONDS = 90

POLL_INTERVAL_SECONDS = 3


def main():
    # -----------------------------------------------------
    # 1. CREATE A UNIQUE DOCUMENT ID
    # -----------------------------------------------------

    # Every test needs a fresh document ID.
    #
    # Otherwise Lambda's duplicate protection may correctly
    # skip a document it has already processed.
    document_id = (
        f"e2e_{uuid4().hex[:8]}"
    )

    print()
    print("=" * 60)
    print("AFTERWARD END-TO-END INGESTION TEST")
    print("=" * 60)

    print()
    print("Patient ID:")
    print(PATIENT_ID)

    print()
    print("Document ID:")
    print(document_id)

    print()
    print("Test PDF:")
    print(FILE_PATH)


    # -----------------------------------------------------
    # 2. UPLOAD DOCUMENT TO S3
    # -----------------------------------------------------

    print()
    print("STEP 1: Uploading document to S3...")

    key = upload_document(
        file_path=FILE_PATH,
        patient_id=PATIENT_ID,
        document_id=document_id,
    )

    print()
    print("✅ Upload successful")
    print("S3 key:")
    print(key)


    # -----------------------------------------------------
    # 3. WAIT FOR ASYNC PIPELINE
    # -----------------------------------------------------

    print()
    print(
        "STEP 2: Waiting for "
        "S3 → SQS → Lambda → Bedrock → DynamoDB..."
    )

    started_at = time.time()


    while True:
        elapsed = (
            time.time()
            - started_at
        )


        # ---------------------------------------------
        # TIMEOUT
        # ---------------------------------------------

        if elapsed > MAX_WAIT_SECONDS:

            print()
            print(
                "❌ TEST FAILED"
            )

            print(
                f"No ready RecoveryState for "
                f"{document_id} after "
                f"{MAX_WAIT_SECONDS} seconds."
            )


            current_state = (
                get_recovery_state(
                    PATIENT_ID
                )
            )

            print()
            print(
                "Current DynamoDB state:"
            )

            print(
                current_state
            )

            print()
            print(
                "Check Lambda logs with:"
            )

            print(
                "aws logs tail "
                "/aws/lambda/"
                "CareLoopDocumentProcessor "
                "--since 10m "
                "--region eu-west-2"
            )

            raise SystemExit(1)


        # ---------------------------------------------
        # READ CURRENT RECOVERYSTATE
        # ---------------------------------------------

        state = get_recovery_state(
            PATIENT_ID
        )


        if not state:

            print(
                f"[{elapsed:.0f}s] "
                "No RecoveryState yet..."
            )

            time.sleep(
                POLL_INTERVAL_SECONDS
            )

            continue


        stored_document_id = (
            state.get(
                "document_id"
            )
        )

        ingestion_status = (
            state.get(
                "ingestion_status"
            )
        )


        print(
            f"[{elapsed:.0f}s] "
            f"document_id="
            f"{stored_document_id}, "
            f"status="
            f"{ingestion_status}"
        )


        # ---------------------------------------------
        # IS THIS OUR NEW DOCUMENT?
        # ---------------------------------------------

        if (
            stored_document_id
            != document_id
        ):
            # This is probably the previous RecoveryState.
            #
            # Keep waiting for the Lambda processing this
            # test document.
            time.sleep(
                POLL_INTERVAL_SECONDS
            )

            continue


        # ---------------------------------------------
        # DOCUMENT IS CURRENTLY PROCESSING
        # ---------------------------------------------

        if (
            ingestion_status
            in {"processing", "indexing"}
        ):

            time.sleep(
                POLL_INTERVAL_SECONDS
            )

            continue


        # ---------------------------------------------
        # DOCUMENT NEEDS ATTENTION
        # ---------------------------------------------

        if (
            ingestion_status
            == "needs_attention"
        ):

            print()
            print(
                "❌ TEST FAILED"
            )

            print(
                "Document reached DynamoDB but "
                "ingestion_status=needs_attention"
            )

            print()
            print(state)

            raise SystemExit(1)


        # ---------------------------------------------
        # SUCCESS
        # ---------------------------------------------

        if (
            ingestion_status
            == "ready"
        ):

            duration = (
                time.time()
                - started_at
            )

            print()
            print("=" * 60)
            print("✅ FULL PIPELINE TEST PASSED")
            print("=" * 60)

            print()
            print(
                f"Completed in "
                f"{duration:.1f} seconds"
            )

            print()
            print(
                "Document ID:"
            )
            print(
                stored_document_id
            )

            print()
            print(
                "Ingestion status:"
            )
            print(
                ingestion_status
            )


            # -----------------------------------------
            # PRINT EXTRACTION SUMMARY
            # -----------------------------------------

            medications = (
                state.get(
                    "medications",
                    [],
                )
            )

            tasks = (
                state.get(
                    "tasks",
                    [],
                )
            )

            appointments = (
                state.get(
                    "appointments",
                    [],
                )
            )

            restrictions = (
                state.get(
                    "restrictions",
                    [],
                )
            )

            monitoring = (
                state.get(
                    "monitoring",
                    [],
                )
            )

            warning_signs = (
                state.get(
                    "warning_signs",
                    [],
                )
            )


            print()
            print("Extracted:")
            print(
                f"  Medications: "
                f"{len(medications)}"
            )

            print(
                f"  Tasks: "
                f"{len(tasks)}"
            )

            print(
                f"  Appointments: "
                f"{len(appointments)}"
            )

            print(
                f"  Restrictions: "
                f"{len(restrictions)}"
            )

            print(
                f"  Monitoring: "
                f"{len(monitoring)}"
            )

            print(
                f"  Warning signs: "
                f"{len(warning_signs)}"
            )


            print()
            print(
                "The following path is proven:"
            )

            print(
                "PDF → S3 → SQS → Lambda "
                "→ Bedrock → normalize "
                "→ validate → DynamoDB"
            )

            return


        # ---------------------------------------------
        # UNKNOWN STATUS
        # ---------------------------------------------

        print(
            f"Unknown ingestion status: "
            f"{ingestion_status}"
        )

        time.sleep(
            POLL_INTERVAL_SECONDS
        )


if __name__ == "__main__":
    main()
