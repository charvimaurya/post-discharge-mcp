// Beneath the Today plan: the way to the weekly dashboard, which shows the history itself.
export function WeekPanel() {
  return <section className="week-panel" aria-label="Weekly dashboard">
    {/* A new tab, so the chat and Today plan stay as they are in this one. */}
    <a className="week-link" href="/demo/recovery" target="_blank" rel="noopener">View weekly dashboard <span aria-hidden="true">↗</span>
      <span className="week-sr"> (opens in a new tab)</span></a>
  </section>;
}
