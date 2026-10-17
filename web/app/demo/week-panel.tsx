import { weekDayLabel, type WeekSummary } from '../../lib/week-summary';

export function WeekPanel({ summary, loading, error, onRefresh }: {
  summary: WeekSummary | null; loading: boolean; error: boolean; onRefresh: () => void;
}) {
  return <section className="week-panel" aria-labelledby="week-heading" aria-busy={loading}>
    <details className="week-disclosure">
      <summary className="week-toggle"><span id="week-heading">This week</span>
        <span className="week-inline-summary">{loading ? 'Checking history…'
          : error || !summary ? 'Summary unavailable'
          : `${summary.completedDays} of 7 mornings confirmed`}</span>
      </summary>
    <div className="week-heading">
      <button type="button" className="back" disabled={loading} onClick={onRefresh}>Refresh</button></div>
    <div aria-live="polite">
      {loading ? <p className="week-note">Checking this week's history…</p>
        : error || !summary ? <p className="week-note">The weekly summary could not be checked. Please try Refresh.</p>
        : <>
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
