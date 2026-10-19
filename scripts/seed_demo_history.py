"""
Fill past days of the demo patient's history, so the weekly dashboard is not empty.

For each date given (before today), save what a well-kept day looks like: the day's
schedule snapshots, every scheduled dose taken and every task done. The
medicines and tasks come from Margaret's current plan for that date, so a new letter
needs a new run. See app/demo_history.py. demo_patient_001 only.

Writes to the live Event History table. Reset demo does not remove these days (it
clears today only); uploading a new letter does. Run with the demo clock, so "today"
is the demo day:

    CLOCK_MODE=demo DEMO_FIXED_NOW=2026-10-23T07:00:00+01:00 \
        python scripts/seed_demo_history.py --dates 2026-10-21 2026-10-22            # preview
    CLOCK_MODE=demo DEMO_FIXED_NOW=2026-10-23T07:00:00+01:00 \
        python scripts/seed_demo_history.py --dates 2026-10-21 2026-10-22 --confirm  # write
    python scripts/seed_demo_history.py --remove                                     # undo
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.clock import get_current_date  # noqa: E402
from app.database import event_history  # noqa: E402
from app.database.recovery_state import DEFAULT_TIMEZONE, get_medications, get_recovery_state, get_today_tasks  # noqa: E402
from app.demo_history import KEY_PREFIX, PATIENT_ID, build_demo_day  # noqa: E402


def remove() -> int:
    seeded = [e for e in event_history.get_complete_patient_events(PATIENT_ID)
              if str(e.get("idempotency_key", "")).startswith(KEY_PREFIX)]
    for event in seeded:
        event_history.event_table.delete_item(Key={"patient_id": PATIENT_ID, "timestamp": event["timestamp"]})
    return len(seeded)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dates", nargs="+", default=[], help="Past dates to fill, YYYY-MM-DD")
    parser.add_argument("--confirm", action="store_true", help="Write the events. Without it, only a preview.")
    parser.add_argument("--remove", action="store_true", help="Delete every event this script saved.")
    args = parser.parse_args()

    if args.remove:
        print(f"Removed {remove()} demo history events for {PATIENT_ID}.")
        return

    state = get_recovery_state(PATIENT_ID)
    if not state:
        raise SystemExit(f"{PATIENT_ID} has no plan. Load her letter first.")
    timezone = state.get("timezone") or DEFAULT_TIMEZONE
    today = get_current_date(timezone)
    if not args.dates:
        raise SystemExit("Give the past dates to fill, for example --dates 2026-10-21 2026-10-22")

    planned = []
    for day in args.dates:
        events = build_demo_day(day, today, get_medications(PATIENT_ID, day), get_today_tasks(PATIENT_ID, day), timezone)
        kinds = [kind for kind, _, _ in events]
        print(f"{day}: {kinds.count('medication_taken')} doses taken, "
              f"{kinds.count('task_completed')} tasks done, {sum(k.endswith('snapshot') for k in kinds)} schedule snapshots")
        planned.extend(events)

    if not args.confirm:
        print(f"Preview only (today is {today}). Nothing was written. Re-run with --confirm.")
        return

    created = sum(event_history.append_event(PATIENT_ID, kind, details, key)["created"] for kind, details, key in planned)
    print(f"Saved {created} new events ({len(planned) - created} were already there).")


if __name__ == "__main__":
    main()
