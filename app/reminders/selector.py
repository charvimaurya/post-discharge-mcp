def find_due_reminder(patient_id, now):
    today = now.date().isoformat()

    tasks = get_today_tasks(patient_id, today)
    medications = get_medications(patient_id, today)

    candidates = []

    for occurrence in tasks + medications:
        if occurrence.get("status") != "pending":
            continue

        clock_time = occurrence.get("clock_time")

        if not clock_time:
            continue

        due_at = datetime.combine(
            now.date(),
            time.fromisoformat(clock_time),
            tzinfo=now.tzinfo,
        )

        reminder_at = due_at - timedelta(minutes=30)

        if reminder_at <= now < due_at:
            candidates.append(occurrence)

    return choose_reminder(candidates)