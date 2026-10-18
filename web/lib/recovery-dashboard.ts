import { readWeekSummary, type WeekDay, type WeekSummary } from './week-summary.ts';

/**
 * The dashboard calendar: it starts on the first day with saved history (or recorded tasks),
 * never later than today, and the remaining tiles of seven are the days ahead. Days before the
 * first saved one are left out rather than shown as empty.
 */
export function calendarDays(week: WeekSummary): { past: WeekDay[]; upcoming: string[] } {
  const tasks = new Map((week.activity || []).map(entry => [entry.date, entry.completedTasks]));
  const first = week.days.findIndex(day => day.hasHistory || (tasks.get(day.date) || 0) > 0);
  const past = week.days.slice(first === -1 ? week.days.length - 1 : first);
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

export async function fetchRecoverySnapshot(selected: string, signal: AbortSignal, fetcher: typeof fetch = fetch) {
  const response = await fetcher('/api/week-summary', { cache: 'no-store', signal });
  if (!response.ok) throw new Error('Unavailable');
  const week = readWeekSummary(await response.json());
  if (!week) throw new Error('Invalid history');
  const date = week.days.some(d => d.date === selected) ? selected : week.days[6].date;
  const details = await fetcher(`/api/recovery-day?date=${date}`, { cache: 'no-store', signal });
  if (!details.ok) throw new Error('Unavailable');
  const day = readRecoveryDay(await details.json(), date);
  if (!day) throw new Error('Invalid history');
  return { week, day, date };
}
