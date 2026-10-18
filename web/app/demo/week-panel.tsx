import { weekDayLabel, type WeekSummary } from '../../lib/week-summary';

export function WeekPanel({ summary, loading, error, onRefresh }: {
  summary: WeekSummary | null; loading: boolean; error: boolean; onRefresh: () => void;
}) {
  return <section className="week-panel" aria-labelledby="week-heading" aria-busy={loading}>
    <details className="week-disclosure">
      <summary className="week-toggle"><a href="/demo/recovery" aria-label="Open recovery dashboard"><span id="week-heading">This week</span>
        <span className="week-inline-summary">{loading ? 'Checking history…'
          : error || !summary ? 'Summary unavailable'
          : `${summary.completedDays} of 7 mornings confirmed`}</span>
      </a></summary>
    <div className="week-heading">
      <button type="button" className="back" disabled={loading} onClick={onRefresh}>Refresh</button></div>
    <div aria-live="polite">
      {loading ? <p className="week-note">Checking this week's history…</p>
        : error || !summary ? <p className="week-note">The weekly summary could not be checked. Please try Refresh.</p>
        : <>
          {summary.activity && <div className="week-activity">
            <p className="week-summary">Recovery tasks recorded complete</p>
            <div className="week-activity-bars" role="group" aria-label="Recorded task completions by day">
              {summary.activity.map(day => <div key={day.date} className="week-activity-day">
                <meter min={0} max={Math.max(1, ...summary.activity!.map(item => item.completedTasks))}
                  value={day.completedTasks} aria-label={`${weekDayLabel(day.date)} ${day.date}: ${day.completedTasks} recovery tasks recorded complete`} />
                <span>{weekDayLabel(day.date)}</span><b>{day.completedTasks}</b>
              </div>)}
            </div>
            <p className="week-note">Saved task records, not a measure of medication adherence.</p>
          </div>}
          <p className="week-summary">Morning medicines</p>
          <ol className="week-days" aria-label="Last seven patient-local days">
            {summary.days.map(day => <li key={day.date} className={`week-day ${day.status}${day.isToday ? ' is-today' : ''}`}
              aria-current={day.isToday ? 'date' : undefined} title={`${day.date}: ${day.label}`}>
              <span>{weekDayLabel(day.date)}</span><b aria-hidden="true">{day.symbol}</b>
              <span className="week-sr">{day.date}: {day.label}{day.isToday ? ', today' : ''}</span>
            </li>)}
          </ol>
          <p className="week-note">✓ Taken · – Recorded missed · ◌ No history · ○ Not yet due · · None scheduled</p>
          {summary.days.some(day => day.status === 'unknown') && <p className="week-note">Missing history does not mean a missed dose.</p>}
          {summary.synthetic && <p className="week-note">Synthetic demo history</p>}
        </>}
    </div>
    </details>
  </section>;
}
