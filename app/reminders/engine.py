"""
Choose the one proactive check-in to make now, or none.

Pure: no AWS, no model. The reminder Lambda loads the plan and saves
the result; this module only decides.

Shared rules
- Deterministic: a check-in is a candidate only while "now" is inside its
  own window, so the same time gives the same check-in.
    timed item (a walk)   from 30 minutes before its clock time until the time
    a time of day's medicines   from 30 minutes before it starts
    missed dose           from 60 minutes after its time of day starts
- Sticky: one check-in at a time. A waiting check-in stays, unchanged, until
  she replies, its item is done, or its window ends. A reload never replaces it.
- "Already sent" stops a check-in being made again. It never brings in an
  item that is outside its own window.
- Quiet hours (default 21:00 to 07:00) and a daily limit (default 6).
- No check-in if she spoke to AfterWard in the last 2 minutes.
- Every check-in has a type, an occurrence_id and a deterministic
  checkin_id; a checkin_id already used today is never used again.
- Fixed priority when several are inside their windows:
  missed dose > follow-on > last day > reminder (walks) > medicines.
- scheduled_checkins on the record ("remind me again in 30 minutes")
  fire once their due_at has passed.

Wording comes from fixed templates, never from a model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Any

from app.agent.completion_replies import medicine_name, step_phrase
from app.agent.next_up import build_next_up, build_steps
from app.agent.occurrence_resolver import item_name, part_of_day
from app.reminders import config
from app.medication_safety import medication_withdrawn
from app.reminders.selector import find_due_reminder
from app.reminders.text import build_opening_greeting, build_reminder_text


PRIORITY = {"missed_dose": 0, "follow_on": 1, "last_day": 2, "reminder": 3, "medicine": 4}

_THIS_PART = {
    "morning": "this morning",
    "midday": "this afternoon",
    "afternoon": "this afternoon",
    "evening": "this evening",
    "bedtime": "this evening",
}


@dataclass
class Checkin:
    type: str
    checkin_id: str
    occurrence_id: str | None
    text: str
    item_type: str | None = None
    slot: str | None = None
    clock_time: str | None = None
    recheck: bool = False
    # The scheduled entry this came from, removed from the record once made.
    scheduled_id: str | None = None
    order: int = 0
    # When its window ends. After this it is cleared, answered or not.
    expires_at: datetime | None = None
    # Every dose a medicines reminder is about (occurrence_id is the first).
    occurrence_ids: list[str] | None = None

    def as_pending(self, today: str, now: datetime) -> dict[str, Any]:
        pending = {
            "checkin_id": self.checkin_id,
            "type": self.type,
            "occurrence_id": self.occurrence_id,
            "item_type": self.item_type,
            "date": today,
            "slot": self.slot,
            "clock_time": self.clock_time,
            "text": self.text,
            "created_at": now.isoformat(),
        }
        if self.recheck:
            pending["recheck"] = True
        if self.occurrence_ids:
            pending["occurrence_ids"] = self.occurrence_ids
        # With no window of its own, it waits an hour for an answer.
        expires = self.expires_at or now + timedelta(minutes=config.UNANSWERED_CHECKIN_MINUTES)
        pending["expires_at"] = expires.isoformat()
        return pending


@dataclass
class Decision:
    checkin: Checkin | None
    reason: str
    candidates: list[Checkin] = field(default_factory=list)
    # The waiting check-in is no longer valid (its item is done or its window
    # ended): the caller clears it. Another may be chosen in the same decision.
    expired: bool = False


def pending_is_valid(
    pending: dict[str, Any],
    tasks: list[dict[str, Any]],
    medications: list[dict[str, Any]],
    now: datetime,
) -> bool:
    """
    Whether a waiting check-in should stay.

    It goes when everything it is about has been ticked, or its window has
    ended. (Her reply clears it elsewhere.) A check-in saved before windows
    were recorded has no expires_at and stays until she replies.
    """

    about = set(pending.get("occurrence_ids") or [pending.get("occurrence_id")]) - {None}
    current = tasks + [o for o in medications if not medication_withdrawn(o)]
    # A referenced dose/task removed from the current plan must not keep an
    # old (possibly grouped) reminder alive after withdrawal or replacement.
    if about and not about.issubset({o.get("occurrence_id") for o in current}):
        return False
    items = [o for o in current if o.get("occurrence_id") in about]

    if items and all(o.get("status") == "completed" for o in items):
        return False

    expires = pending.get("expires_at")

    if expires:
        try:
            return now <= datetime.fromisoformat(str(expires))
        except ValueError:
            return True

    return True


# ---------- Shared gates ----------

def in_quiet_hours(now: datetime) -> bool:
    start, end = config.quiet_hours()
    local = now.time()

    if start <= end:
        return start <= local < end

    return local >= start or local < end


def used_today(state: dict[str, Any], today: str) -> list[str]:
    """checkin_ids already made today."""

    if state.get("checkins_today_date") != today:
        return []

    return list(state.get("checkins_today_ids") or [])


def chatted_recently(state: dict[str, Any], real_now_utc: datetime) -> bool:
    """Real elapsed time since her last message (the demo clock does not move)."""

    last = state.get("last_chat_at")

    if not last:
        return False

    try:
        then = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
    except ValueError:
        return False

    return (real_now_utc - then).total_seconds() < config.recent_chat_seconds()


# ---------- Candidates ----------

def missed_dose_text(first_name: str | None, medicine: str, slot: str | None) -> str:
    when = _THIS_PART.get(slot or "", "today")
    sentence = f"I haven't heard about your {medicine} {when}. Have you taken it?"

    if first_name:
        return f"{first_name}, {sentence}"

    return sentence[0].upper() + sentence[1:]


def recheck_text(first_name: str | None, medicine: str) -> str:
    who = f", {first_name}" if first_name else ""

    return f"Just checking again{who}. Have you taken your {medicine}?"


def _missed_doses(
    medications: list[dict[str, Any]],
    now: datetime,
    today: str,
    first_name: str | None,
) -> list[Checkin]:
    """Scheduled doses not reported an hour after their time of day began, until the next one."""

    slots = list(config.MEDICINE_SLOT_STARTS)
    found = []

    for order, dose in enumerate(medications):
        if dose.get("as_needed") or dose.get("needs_confirmation") or dose.get("status") == "completed":
            continue

        slot = part_of_day(dose)

        if slot not in config.MEDICINE_SLOT_STARTS:
            continue

        starts = datetime.combine(now.date(), config.MEDICINE_SLOT_STARTS[slot], tzinfo=now.tzinfo)
        following = slots.index(slot) + 1
        ends = (
            datetime.combine(now.date(), config.MEDICINE_SLOT_STARTS[slots[following]], tzinfo=now.tzinfo)
            if following < len(slots)
            else datetime.combine(now.date(), time(23, 59), tzinfo=now.tzinfo)
        )

        # Ask only within its own part of the day: never about the
        # morning dose once the midday one has started.
        if not (starts + timedelta(minutes=config.MISSED_DOSE_AFTER_MINUTES) <= now < ends):
            continue

        occurrence_id = dose["occurrence_id"]
        found.append(Checkin(
            type="missed_dose",
            checkin_id=f"{today}#missed_dose#{occurrence_id}",
            occurrence_id=occurrence_id,
            text=missed_dose_text(first_name, medicine_name(item_name(dose)), slot),
            item_type="medication",
            slot=slot,
            order=order,
            expires_at=ends,
        ))

    return found


def medicine_reminder_text(first_name: str | None, doses: list[dict[str, Any]], now: datetime) -> str:
    """'Good morning, Margaret. I hope you slept well. Next is your paracetamol and blood thinner, after breakfast.'"""

    steps = build_steps(build_next_up([], doses, now))

    return f"{build_opening_greeting(first_name, now)} Next is {step_phrase(steps[0])}."


def _medicine_reminders(
    medications: list[dict[str, Any]],
    now: datetime,
    today: str,
    first_name: str | None,
) -> list[Checkin]:
    """
    One reminder for a time of day's medicines, from 30 minutes before it
    starts until the missed-dose question takes over an hour after.
    """

    found = []

    for order, (slot, start) in enumerate(config.MEDICINE_SLOT_STARTS.items()):
        starts = datetime.combine(now.date(), start, tzinfo=now.tzinfo)
        opens = starts - timedelta(minutes=config.MEDICINE_REMINDER_BEFORE_MINUTES)
        closes = starts + timedelta(minutes=config.MISSED_DOSE_AFTER_MINUTES)

        if not (opens <= now < closes):
            continue

        doses = [
            dose for dose in medications
            if part_of_day(dose) == slot
            and dose.get("status") == "pending"
            and not dose.get("as_needed")
            and not dose.get("needs_confirmation")
            # A dose with its own clock time has its own timed reminder.
            and not dose.get("clock_time")
        ]

        if not doses:
            continue

        found.append(Checkin(
            type="medicine",
            checkin_id=f"{today}#medicine#{slot}",
            occurrence_id=doses[0]["occurrence_id"],
            occurrence_ids=[dose["occurrence_id"] for dose in doses],
            text=medicine_reminder_text(first_name, doses, now),
            item_type="medication",
            slot=slot,
            order=order,
            expires_at=closes,
        ))

    return found


def _scheduled(
    state: dict[str, Any],
    tasks: list[dict[str, Any]],
    medications: list[dict[str, Any]],
    now: datetime,
    today: str,
) -> list[Checkin]:
    """Scheduled check-ins that are due today and still make sense."""

    done = {
        o["occurrence_id"] for o in tasks + medications
        if o.get("status") == "completed"
    }
    available = {o.get("occurrence_id") for o in tasks + medications}
    found = []

    for entry in state.get("scheduled_checkins") or []:
        try:
            due = datetime.fromisoformat(str(entry["due_at"]))
        except (KeyError, ValueError):
            continue

        if due.astimezone(now.tzinfo).date().isoformat() != today or due > now:
            continue

        if entry.get("occurrence_id") and entry["occurrence_id"] not in available:
            continue

        # Already done since it was scheduled: nothing to ask.
        if entry.get("occurrence_id") in done:
            continue

        found.append(Checkin(
            type=str(entry.get("type") or "reminder"),
            checkin_id=str(entry["checkin_id"]),
            occurrence_id=entry.get("occurrence_id"),
            text=str(entry["text"]),
            item_type=entry.get("item_type"),
            slot=entry.get("slot"),
            recheck=bool(entry.get("recheck")),
            scheduled_id=str(entry["checkin_id"]),
        ))

    return found


def _walk_reminder(
    tasks: list[dict[str, Any]],
    medications: list[dict[str, Any]],
    now: datetime,
    today: str,
    first_name: str | None,
    force_next: bool,
) -> list[Checkin]:
    """The reminder for an item with a clock time (a walk): from 30 minutes before, until its time."""

    item = find_due_reminder(tasks=tasks, medications=medications, now=now, force_next=force_next)

    if item is None:
        return []

    return [Checkin(
        type="reminder",
        checkin_id=f"{today}#{item['occurrence_id']}",
        occurrence_id=item["occurrence_id"],
        text=build_reminder_text(first_name=first_name, item=item, now=now),
        item_type=item["item_type"],
        clock_time=item.get("clock_time"),
        # Forced for a test, it has no window: it waits like any unanswered check-in.
        expires_at=None if force_next else datetime.combine(
            now.date(), time.fromisoformat(str(item["clock_time"])), tzinfo=now.tzinfo,
        ),
    )]


# ---------- The decision ----------

def choose_checkin(
    state: dict[str, Any],
    tasks: list[dict[str, Any]],
    medications: list[dict[str, Any]],
    now: datetime,
    real_now_utc: datetime,
    first_name: str | None,
    force_next: bool = False,
) -> Decision:
    """
    The check-in to make now, or None with the reason.

    force_next (a test hook) skips the gates and the reminder window,
    and only looks at the next walk-style reminder.
    """

    medications = [dose for dose in medications if not medication_withdrawn(dose)]
    today = now.date().isoformat()

    if force_next:
        found = _walk_reminder(tasks, medications, now, today, first_name, force_next=True)
        return Decision(found[0] if found else None, "created" if found else "nothing_due", found)

    pending = state.get("pending_checkin")
    expired = False

    if pending:
        # Sticky: a waiting check-in is never replaced while it is still valid.
        if pending_is_valid(pending, tasks, medications, now):
            return Decision(None, "checkin_waiting")
        expired = True

    if in_quiet_hours(now):
        return Decision(None, "quiet_hours", expired=expired)

    if chatted_recently(state, real_now_utc):
        return Decision(None, "recent_chat", expired=expired)

    used = used_today(state, today)

    if len(used) >= config.max_checkins_per_day():
        return Decision(None, "daily_limit", expired=expired)

    # Only what is inside its own window right now.
    candidates = (
        _scheduled(state, tasks, medications, now, today)
        + _missed_doses(medications, now, today, first_name)
        + _walk_reminder(tasks, medications, now, today, first_name, force_next=False)
        + _medicine_reminders(medications, now, today, first_name)
    )
    fresh = [
        c for c in candidates
        if c.checkin_id not in used and c.checkin_id != state.get("last_checkin_key")
    ]

    if not fresh:
        return Decision(None, "already_reminded" if candidates else "nothing_due", candidates, expired=expired)

    fresh.sort(key=lambda c: (PRIORITY.get(c.type, 9), c.order))

    return Decision(fresh[0], "created", candidates, expired=expired)
