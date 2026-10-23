export type WeekStatus = 'completed' | 'missed' | 'unknown' | 'not_yet_due' | 'no_scheduled_morning_doses';
// hasHistory: the day has saved schedule evidence (a snapshot, or today's own occurrences).
export type WeekDay = { date: string; isToday: boolean; status: WeekStatus; label: string; symbol: string; hasHistory: boolean };
export type WeekActivity = { date: string; completedTasks: number };
export type WeekSummary = { days: WeekDay[]; completedDays: number; synthetic: boolean; activity?: WeekActivity[]; dischargeDate?: string };

const states: Record<WeekStatus, { label: string; symbol: string }> = {
  completed: { label: 'All morning medicines recorded as taken', symbol: '✓' },
  missed: { label: 'Explicitly recorded missed dose', symbol: '–' },
  unknown: { label: 'Not enough history to confirm', symbol: '◌' },
  not_yet_due: { label: 'Morning medicines not yet due', symbol: '○' },
  no_scheduled_morning_doses: { label: 'No morning medicines scheduled', symbol: '·' },
};

function object(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value);
}

/** Fail closed on malformed history; never interpret missing evidence as a miss. */
export function readWeekSummary(payload: unknown): WeekSummary | null {
  if (!object(payload) || !object(payload.week) || !Array.isArray(payload.week.days)
      || payload.week.days.length !== 7) return null;
  const days: WeekDay[] = [];
  for (const entry of payload.week.days) {
    if (!object(entry) || typeof entry.date !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(entry.date)
        || typeof entry.status !== 'string' || !Object.hasOwn(states, entry.status)
        || typeof entry.is_today !== 'boolean') return null;
    const stamp = Date.parse(`${entry.date}T00:00:00Z`);
    if (!Number.isFinite(stamp) || new Date(stamp).toISOString().slice(0, 10) !== entry.date
        || (days.length && stamp - Date.parse(`${days.at(-1)!.date}T00:00:00Z`) !== 86_400_000)) return null;
    const status = entry.status as WeekStatus;
    if (entry.is_today !== (days.length === 6)) return null;
    const hasHistory = entry.schedule_evidence === 'snapshot' || entry.schedule_evidence === 'current_day_occurrences';
    days.push({ date: entry.date, isToday: entry.is_today, status, ...states[status], hasHistory });
  }
  let activity: WeekActivity[] | undefined;
  if (Array.isArray(payload.week.activity) && payload.week.activity.length === 7
      && payload.week.activity.every((entry, index) => object(entry) && entry.date === days[index].date
        && Number.isSafeInteger(entry.completed_tasks) && Number(entry.completed_tasks) >= 0)) {
    activity = payload.week.activity.map(entry => ({ date: entry.date as string, completedTasks: entry.completed_tasks as number }));
  }
  const discharge = payload.week.discharge_date;
  const dischargeDate = typeof discharge === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(discharge)
    && Number.isFinite(Date.parse(`${discharge}T12:00:00Z`))
    && new Date(`${discharge}T12:00:00Z`).toISOString().slice(0, 10) === discharge ? discharge : undefined;
  return { days, completedDays: days.filter(day => day.status === 'completed').length, ...(activity ? { activity } : {}),
    ...(dischargeDate ? { dischargeDate } : {}),
    synthetic: payload.week.synthetic_demo_history === true };
}

export function weekDayLabel(date: string): string {
  // Dates already represent patient-local calendar days. Do not shift them to browser time.
  return new Date(`${date}T12:00:00Z`).toLocaleDateString('en-GB', { weekday: 'short', timeZone: 'UTC' });
}
