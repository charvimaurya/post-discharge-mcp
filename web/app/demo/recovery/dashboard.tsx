// The weekly recovery dashboard, in the same panels, cards and chips as the Today screen.
// The page (page.tsx) supplies the top bar, footer and scaled frame.
import { weekDayLabel, type WeekSummary } from '../../../lib/week-summary';
import { recordedTime, recoveryStatus, type RecoveryDay, type RecoveryEntry } from '../../../lib/recovery-dashboard';

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

function Entry({ entry, detail, timezone }: { entry: RecoveryEntry; detail: string; timezone: string }) {
  const style = look[entry.status] || look.unknown;
  return <div className={`item ${style.item}`}>
    <div className="ico" aria-hidden="true">{style.symbol}</div>
    <div className="t"><b>{entry.name || 'Name unavailable'}</b>
      <span className="d">{detail}</span>
      {entry.needs_confirmation && <span className="d"><span className="chip amber">Needs confirmation</span></span>}
    </div>
    <div className="recovery-when"><span className={`chip ${style.chip}`}>{recoveryStatus[entry.status]}</span>
      <small>{recordedTime(entry.recorded_at, timezone)}</small></div>
  </div>;
}

export function RecoveryDashboard({ week, day, selected, loading, error, onSelect, onRefresh }: {
  week: WeekSummary | null; day: RecoveryDay | null; selected: string; loading: boolean; error: boolean;
  onSelect: (date: string) => void; onRefresh: () => void;
}) {
  const tasksDone = week?.activity ? week.activity.reduce((n, d) => n + d.completedTasks, 0) : null;
  const shown = day && day.date === selected ? day : null;
  const selectedDay = week?.days.find(d => d.date === selected);
  return <div className="stage recovery-stage">
    <div className="panel recovery-week">
      <div className="th">
        <div><div className="eyebrow">{week ? `${weekDayLabel(week.days[0].date)} ${week.days[0].date.slice(-2)} – ${weekDayLabel(week.days[6].date)} ${week.days[6].date.slice(-2)}` : 'Last 7 days'}</div>
          <h2>This week</h2></div>
        <button type="button" className="back" onClick={onRefresh} disabled={loading}>Refresh</button>
      </div>
      <div className="tbody" tabIndex={0} role="region" aria-label="Weekly summary">
        <div aria-live="polite">{error ? <p className="recovery-alert" role="alert">Recovery history could not be checked. Please try Refresh.</p>
          : loading && !week ? <p className="note">Checking saved records…</p> : null}</div>
        {week && <>
          <section className="recovery-stats" aria-label="Weekly totals">
            <div><b>{week.completedDays}<span> of 7</span></b><p>Mornings confirmed</p></div>
            <div><b>{tasksDone ?? '–'}</b><p>Tasks recorded complete</p></div>
            <div><b>{week.days.filter(d => d.status === 'unknown').length}</b><p>Days with incomplete history</p></div>
          </section>
          <div className="slot-h">Choose a day</div>
          <nav className="recovery-days" aria-label="Choose a recovery date">
            {week.days.map(d => <button key={d.date} type="button" className={`week-day ${d.status}`} aria-pressed={selected === d.date}
              aria-current={d.isToday ? 'date' : undefined} onClick={() => onSelect(d.date)}
              aria-label={`${d.date}, ${d.label}${d.isToday ? ', today' : ''}`}>
              <span>{weekDayLabel(d.date)}</span><b>{d.date.slice(-2)}</b><i aria-hidden="true">{d.symbol}</i>
              <small>{d.isToday ? 'Today' : ' '}</small>
            </button>)}
          </nav>
          <p className="week-note">✓ Taken · – Recorded missed · ◌ No history · ○ Not yet due · · None scheduled</p>
          <p className="week-note">Morning medicines only. Missing history does not mean a missed dose.</p>
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
            : <div className="items">{shown.tasks.map(t => <Entry key={t.occurrence_id} entry={{ ...t, name: t.name || 'Recorded recovery task' }}
                timezone={shown.timezone} detail={t.period || 'Any time'} />)}</div>}
          <p className="week-note recovery-tz">Times shown in {shown.timezone}.</p>
        </>}
      </div>
    </div>
  </div>;
}
