// The weekly recovery dashboard, in the same panels, cards and chips as the Today screen.
// The page (page.tsx) supplies the top bar, footer and scaled frame.
import { weekDayLabel, type WeekSummary } from '../../../lib/week-summary';
import { calendarDays, dayProgress, recordedTime, recoveryStatus, type RecoveryDay, type RecoveryEntry } from '../../../lib/recovery-dashboard';

// Card and chip look for each saved status; anything unrecorded stays neutral grey.
const look: Record<string, { item: string; chip: string; symbol: string }> = {
  taken: { item: 'ok', chip: 'blue', symbol: '✓' }, completed: { item: 'ok', chip: 'blue', symbol: '✓' },
  missed: { item: 'missed', chip: 'amber', symbol: '–' },
  unknown: { item: '', chip: 'grey', symbol: '◌' }, not_yet_due: { item: '', chip: 'grey', symbol: '○' },
};

// Dates are already patient-local calendar days; format them without shifting to browser time.
function longDate(date: string): string {
  return new Date(`${date}T12:00:00Z`).toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long', timeZone: 'UTC' });
}

// A task's line: when to do it (the letter's clock time, else its part of the day) and,
// for a task done more than once that day, which one it is, as on the Today page ("1 of 3").
function taskDetails(tasks: RecoveryEntry[]): string[] {
  const totals = new Map<string, number>();
  tasks.forEach(t => totals.set(t.name || '', (totals.get(t.name || '') || 0) + 1));
  const seen = new Map<string, number>();
  return tasks.map(t => {
    const when = t.period ? t.period.charAt(0).toUpperCase() + t.period.slice(1) : 'Any time';
    const total = totals.get(t.name || '') || 1;
    const nth = (seen.get(t.name || '') || 0) + 1;
    seen.set(t.name || '', nth);
    return total > 1 ? `${when} · ${nth} of ${total}` : when;
  });
}

function Entry({ entry, detail, timezone }: { entry: RecoveryEntry; detail: string; timezone: string }) {
  const style = look[entry.status] || look.unknown;
  return <div className={`item ${style.item}`}>
    <div className="ico" aria-hidden="true">{style.symbol}</div>
    <div className="t"><b>{entry.name || 'Name unavailable'}</b>
      <span className="d">{detail}</span>
      {entry.needs_confirmation && <span className="d"><span className="chip amber">Needs confirmation</span></span>}
    </div>
    {/* Nothing recorded yet: no status label, the plain card says enough. */}
    {entry.status !== 'unknown' && <div className="recovery-when"><span className={`chip ${style.chip}`}>{recoveryStatus[entry.status]}</span>
      <small>{recordedTime(entry.recorded_at, timezone)}</small></div>}
  </div>;
}

// A calendar tile: the whole day done, part of it, or nothing recorded (still loading counts as nothing).
const progressLook = {
  complete: { className: 'completed', symbol: '✓', label: 'All done' },
  in_progress: { className: 'in-progress', symbol: '◐', label: 'In progress' },
  none: { className: 'unknown', symbol: '◌', label: 'Nothing recorded' },
} as const;

export function RecoveryDashboard({ week, day, days = {}, selected, loading, error, onSelect }: {
  week: WeekSummary | null; day: RecoveryDay | null; days?: Record<string, RecoveryDay>; selected: string;
  loading: boolean; error: boolean; onSelect: (date: string) => void;
}) {
  const calendar = week ? calendarDays(week) : null;
  const tiles = calendar ? [...calendar.past.map(d => d.date), ...calendar.upcoming] : [];
  const shown = day && day.date === selected ? day : null;
  // Each day is counted like the Today page's "x of 13": every task and scheduled medicine dose.
  const progress = (date: string) => {
    const details = days[date] || (shown && shown.date === date ? shown : null);
    return details ? dayProgress(details) : { done: 0, total: 0, state: 'none' as const };
  };
  const { done: dayDone, total: dayTotal } = shown ? dayProgress(shown) : { done: 0, total: 0 };
  const selectedDay = week?.days.find(d => d.date === selected);
  return <div className="stage recovery-stage">
    <div className="panel recovery-week">
      <div className="th">
        <div><div className="eyebrow">{tiles.length ? `${weekDayLabel(tiles[0])} ${tiles[0].slice(-2)} – ${weekDayLabel(tiles[tiles.length - 1])} ${tiles[tiles.length - 1].slice(-2)}` : 'Last 7 days'}</div>
          <h2>This week</h2></div>
      </div>
      <div className="tbody" tabIndex={0} role="region" aria-label="Weekly summary">
        <div aria-live="polite">{error ? <p className="recovery-alert" role="alert">Recovery history could not be checked. It will try again in a moment.</p>
          : loading && !week ? <p className="note">Checking saved records…</p> : null}</div>
        {week && calendar && <>
          <section className="recovery-stats" aria-label="Weekly totals">
            <div><b>{calendar.past.filter(d => progress(d.date).state === 'complete').length}/{tiles.length}</b><p>Days completed</p></div>
            <div><b>{dayTotal ? `${dayDone}/${dayTotal}` : '–'}</b><p>Tasks completed</p>
              <small>{selected ? `${weekDayLabel(selected)} ${selected.slice(-2)}` : 'Choose a day'}</small></div>
          </section>
          <div className="slot-h">Choose a day</div>
          <nav className="recovery-days" aria-label="Choose a recovery date">
            {calendar.past.map(d => { const look = progressLook[progress(d.date).state]; return <button key={d.date} type="button"
              className={`week-day ${look.className}`} aria-pressed={selected === d.date}
              aria-current={d.isToday ? 'date' : undefined} onClick={() => onSelect(d.date)}
              aria-label={`${d.date}, ${look.label}${d.isToday ? ', today' : ''}`}>
              <span>{weekDayLabel(d.date)}</span><b>{d.date.slice(-2)}</b><i aria-hidden="true">{look.symbol}</i>
              <small>{d.isToday ? 'Today' : ' '}</small>
            </button>; })}
            {/* Days ahead have no history yet, so they cannot be opened. */}
            {calendar.upcoming.map(date => <button key={date} type="button" className="week-day upcoming" aria-pressed={false}
              disabled aria-label={`${date}, upcoming`}>
              <span>{weekDayLabel(date)}</span><b>{date.slice(-2)}</b><i aria-hidden="true">·</i>
              <small>Upcoming</small>
            </button>)}
          </nav>
          <p className="week-note">✓ All done · ◐ In progress · ◌ Nothing recorded</p>
          <p className="week-note">A day is done when every task and medicine dose that day is recorded.</p>
        </>}
      </div>
      <div className="letter-actions">
        {/* Opened in its own tab from Today: close it to return to the chat. If the browser keeps the tab
            open (it was opened some other way), the link opens Today directly instead of the upload screen. */}
        <a className="letter-back" href="/demo?view=today" onClick={() => { if (window.history.length === 1) window.close(); }}>
          <span className="letter-back-arrow" aria-hidden="true">→</span>Back to Today</a>
        <span>Saved records, not a clinical score</span>
      </div>
    </div>

    <div className="panel grow recovery-day">
      <div className="th">
        <div><div className="eyebrow rose">{selected ? `${longDate(selected)}${selectedDay?.isToday ? ' · Today' : ''}` : 'Day details'}</div>
          <h2>Day details</h2></div>
        {shown?.synthetic_demo_history && <span className="chip blue recovery-provenance">Synthetic demo history</span>}
      </div>
      <div className="tbody" tabIndex={0} role="region" aria-label={selected ? `Recovery details for ${selected}` : 'Recovery details'}>
        {!shown ? <p className="note">{error ? 'Details are unavailable until the history can be checked.' : 'Checking saved records…'}</p> : <>
          <div className="slot-h">Medicines</div>
          {shown.scope === 'morning_only' && <p className="week-note recovery-gap">Only morning schedules are kept for past days. Other doses have not been reconstructed.</p>}
          {shown.schedule_evidence === 'missing_or_conflicting'
            ? <p className="note">Not enough historical schedule evidence to list medicines safely.</p>
            : !shown.medications.length ? <p className="note">No scheduled medicines in the available schedule. As-needed medicines are excluded.</p>
            : <div className="items">{shown.medications.map(m => <Entry key={m.occurrence_id} entry={m} timezone={shown.timezone}
                detail={[m.dose || 'Dose not recorded', m.period || 'Time unspecified'].join(' · ')} />)}</div>}
          <div className="slot-h">Recovery tasks</div>
          {!shown.tasks.length ? <p className="note">No saved task activity or task schedule for this date.</p>
            : <div className="items">{shown.tasks.map((t, i) => <Entry key={t.occurrence_id} entry={{ ...t, name: t.name || 'Recorded recovery task' }}
                timezone={shown.timezone} detail={taskDetails(shown.tasks)[i]} />)}</div>}
          <p className="week-note recovery-tz">Times shown in {shown.timezone}.</p>
        </>}
      </div>
    </div>
  </div>;
}
