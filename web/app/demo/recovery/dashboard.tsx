import { weekDayLabel, type WeekSummary } from '../../../lib/week-summary';
import { recordedTime, recoveryStatus, type RecoveryDay } from '../../../lib/recovery-dashboard';

export function RecoveryDashboard({ week, day, selected, loading, error, onSelect, onRefresh }: {
  week: WeekSummary | null; day: RecoveryDay | null; selected: string; loading: boolean; error: boolean;
  onSelect: (date: string) => void; onRefresh: () => void;
}) {
  return <main className="recovery-shell">
    <header><a href="/demo">← Back to Today</a><span>AfterWard</span></header>
    <div className="recovery-title"><div><p>Your recorded recovery</p><h1>Recovery dashboard</h1></div>
      <button onClick={onRefresh} disabled={loading}>Refresh</button></div>
    <p className="recovery-note">Saved records, not a clinical recovery score. Missing history does not mean a missed dose.</p>
    <div aria-live="polite">{error ? <p role="alert">Recovery history could not be checked. Please try Refresh.</p>
      : loading ? <p>Checking saved records…</p> : null}</div>
    {week && <>
      <section className="recovery-cards" aria-label="Weekly summary">
        <article><b>{week.completedDays} of 7</b><p>Mornings confirmed</p><small>All evidenced scheduled morning doses recorded taken</small></article>
        <article><b>{week.activity ? week.activity.reduce((n, d) => n + d.completedTasks, 0) : 'Unavailable'}</b><p>Recovery tasks recorded complete</p><small>Task events counted separately from medicines</small></article>
        <article><b>{week.days.filter(d => d.status === 'unknown').length}</b><p>Days with incomplete medicine history</p><small>Not counted as missed</small></article>
      </section>
      <nav className="recovery-calendar" aria-label="Choose a recovery date">
        {week.days.map(d => <button key={d.date} type="button" aria-pressed={selected === d.date}
          aria-current={d.isToday ? 'date' : undefined} onClick={() => onSelect(d.date)}
          aria-label={`${d.date}, ${d.label}${d.isToday ? ', today' : ''}`}>
          <span>{weekDayLabel(d.date)}</span><b>{d.date.slice(-2)}</b><span>{d.symbol}</span><small>{d.isToday ? 'Today' : d.date.slice(0, 7)}</small>
        </button>)}
      </nav>
      <p className="recovery-note">✓ Taken · – Recorded missed · ◌ No history · ○ Not yet due · · None scheduled</p>
    </>}
    {day && day.date === selected && <section aria-label={`Recovery details for ${selected}`}>
      <h2>{selected}</h2><p className="recovery-note">Times shown in {day.timezone}.</p>
      {day.synthetic_demo_history && <p className="recovery-provenance">Synthetic demo history</p>}
      <div className="recovery-grid"><article className="recovery-detail"><h3>Scheduled medicines</h3>
        {day.scope === 'morning_only' && <p className="recovery-note">Only historical morning schedules are available. Other doses have not been reconstructed.</p>}
        {day.schedule_evidence === 'missing_or_conflicting' ? <p>Not enough historical schedule evidence to list medicines safely.</p>
          : !day.medications.length ? <p>No scheduled medicines in the available schedule. As-needed medicines are excluded.</p>
          : <div className="recovery-table-wrap"><table><thead><tr><th>Medicine</th><th>Scheduled dose</th><th>Status</th><th>Recorded time</th></tr></thead>
            <tbody>{day.medications.map(m => <tr key={m.occurrence_id}><td>{m.name || 'Name unavailable'}</td>
              <td>{m.dose || 'Dose not recorded'}<small>{m.period || 'Time unspecified'}</small>
                {m.needs_confirmation && <small>Needs confirmation</small>}</td>
              <td><span className={`recovery-status ${m.status}`}>{recoveryStatus[m.status]}</span></td>
              <td>{recordedTime(m.recorded_at, day.timezone)}</td></tr>)}</tbody></table></div>}
      </article><article className="recovery-detail"><h3>Recovery task activity</h3>
        {!day.tasks.length ? <p>No saved task activity or historical task schedule for this date.</p>
          : <ul>{day.tasks.map(t => <li key={t.occurrence_id}><b>{t.name || 'Recorded recovery task'}</b>
            <span className={`recovery-status ${t.status}`}>{recoveryStatus[t.status]}</span>
            <small>{recordedTime(t.recorded_at, day.timezone)}</small></li>)}</ul>}
      </article></div>
    </section>}
  </main>;
}
