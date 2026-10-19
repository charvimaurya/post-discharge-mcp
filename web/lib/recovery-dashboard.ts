import { readWeekSummary, type WeekDay, type WeekSummary } from './week-summary.ts';

// The dashboard calendar: the two days before today, today, then the days ahead (seven tiles).
export const DAYS_BEFORE_TODAY = 2;

export function calendarDays(week: WeekSummary): { past: WeekDay[]; upcoming: string[] } {
  const past = week.days.slice(-(DAYS_BEFORE_TODAY + 1));
  const today = Date.parse(`${week.days[week.days.length - 1].date}T12:00:00Z`);
  const upcoming = Array.from({ length: week.days.length - past.length },
    (_, i) => new Date(today + (i + 1) * 86_400_000).toISOString().slice(0, 10));
  return { past, upcoming };
}

export type RecoveryEntry = { occurrence_id: string; name: string | null; status: string; recorded_at: string | null;
  dose?: string | null; period?: string | null; due_at?: string | null; needs_confirmation?: boolean };
export type RecoveryDay = { date: string; timezone: string; schedule_evidence: string; scope: string;
  synthetic_demo_history: boolean; medications: RecoveryEntry[]; tasks: RecoveryEntry[] };
export const recoveryStatus: Record<string, string> = {
  taken: 'Recorded taken', completed: 'Recorded complete', missed: 'Recorded missed',
  unknown: 'Not enough evidence', not_yet_due: 'Not yet due',
};
const object = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value);
export function readRecoveryDay(value: unknown, expectedDate: string): RecoveryDay | null {
  if (!object(value) || value.kind !== 'recovery_day_details' || value.schema_version !== 1
      || value.date !== expectedDate || typeof value.timezone !== 'string'
      || !['snapshot', 'current_day_occurrences', 'missing_or_conflicting'].includes(String(value.schedule_evidence))
      || !['morning_only', 'all_scheduled'].includes(String(value.scope))) return null;
  try { new Intl.DateTimeFormat('en-GB', { timeZone: value.timezone }); } catch { return null; }
  for (const field of ['medications', 'tasks']) {
    const entries = value[field];
    if (!Array.isArray(entries)) return null;
    const ids = new Set<string>();
    for (const entry of entries) {
      if (!object(entry) || typeof entry.occurrence_id !== 'string' || ids.has(entry.occurrence_id)
          || entry.occurrence_id.split('#').at(-2) !== expectedDate
          || typeof entry.status !== 'string' || !Object.hasOwn(recoveryStatus, entry.status)
          || (field === 'tasks' ? !['completed', 'unknown', 'not_yet_due', 'missed'].includes(entry.status)
            : entry.status === 'completed')
          || !['name', 'dose', 'period', 'due_at'].every(key => entry[key] == null || typeof entry[key] === 'string')
          || (entry.needs_confirmation !== undefined && typeof entry.needs_confirmation !== 'boolean')
          || (entry.recorded_at !== null && (typeof entry.recorded_at !== 'string'
            || !/(Z|[+-]\d\d:\d\d)$/.test(entry.recorded_at) || !Number.isFinite(Date.parse(entry.recorded_at))))
          || (['taken', 'completed', 'missed'].includes(entry.status) && !entry.recorded_at)) return null;
      ids.add(entry.occurrence_id);
    }
  }
  return value as unknown as RecoveryDay;
}
export function recordedTime(stamp: string | null, timezone: string): string {
  return stamp ? new Intl.DateTimeFormat('en-GB', { timeZone: timezone, dateStyle: 'medium', timeStyle: 'short' }).format(new Date(stamp)) : 'No confirmed record';
}

// How much of a day's plan is recorded done, counted like the Today page: every task and
// scheduled medicine dose that day (as-needed medicines are not listed).
export type DayProgress = { done: number; total: number; state: 'complete' | 'in_progress' | 'none' };
export function dayProgress(day: RecoveryDay): DayProgress {
  const total = day.tasks.length + day.medications.length;
  const done = day.tasks.filter(t => t.status === 'completed').length + day.medications.filter(m => m.status === 'taken').length;
  return { done, total, state: total > 0 && done === total ? 'complete' : done > 0 ? 'in_progress' : 'none' };
}

/** The week, plus the details of every day on the calendar up to today (the selected one included). */
export async function fetchRecoverySnapshot(selected: string, signal: AbortSignal, fetcher: typeof fetch = fetch) {
  const response = await fetcher('/api/week-summary', { cache: 'no-store', signal });
  if (!response.ok) throw new Error('Unavailable');
  const week = readWeekSummary(await response.json());
  if (!week) throw new Error('Invalid history');
  const dates = calendarDays(week).past.map(d => d.date);
  const date = dates.includes(selected) ? selected : dates[dates.length - 1];
  const days = Object.fromEntries(await Promise.all(dates.map(async when => {
    const details = await fetcher(`/api/recovery-day?date=${when}`, { cache: 'no-store', signal });
    if (!details.ok) throw new Error('Unavailable');
    const parsed = readRecoveryDay(await details.json(), when);
    if (!parsed) throw new Error('Invalid history');
    return [when, parsed] as const;
  }))) as Record<string, RecoveryDay>;
  return { week, day: days[date], date, days };
}
