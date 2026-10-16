"""
Reset the AfterWard demo patient to a clean "nothing done yet" state.

The reset itself lives in app/demo_reset.py, shared with the bridge's
POST /reset route (the "Reset demo" button on /demo). See that module
for exactly what is and is not changed. demo_patient_001 ONLY.

Usage:

    python scripts/reset_demo_patient.py --confirm
"""

import argparse
import sys
from pathlib import Path

# Support direct execution from scripts/ without requiring package installation.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import config
from app.demo_reset import PATIENT_ID, NoPlanToReset, reset_demo_patient


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            f"Reset {PATIENT_ID}: delete current-date completions and "
            "clear completion state. The recovery plan is kept."
        ),
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required. Without it, nothing is changed.",
    )
    args = parser.parse_args()

    if not args.confirm:
        print(
            f"This will delete current-date completions for {PATIENT_ID} "
            f"in {config.EVENT_HISTORY_TABLE} and reset completion "
            f"state in {config.RECOVERY_STATE_TABLE}.\n"
            "Nothing was changed. Re-run with --confirm:\n\n"
            "    python scripts/reset_demo_patient.py --confirm"
        )
        sys.exit(1)

    try:
        result = reset_demo_patient()
    except NoPlanToReset as exc:
        raise SystemExit(str(exc))

    print(f"Patient reset:               {PATIENT_ID}")
    print(f"Event History items deleted: {result['events_deleted']}")
    print(f"Tasks reset:                 {result['tasks_reset']}")
    print(f"Medications reset:           {result['medications_reset']}")


if __name__ == "__main__":
    main()
