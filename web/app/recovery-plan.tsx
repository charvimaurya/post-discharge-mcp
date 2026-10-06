// Present schema fields in a predictable order without deriving clinical instructions.
import type { RecoveryState } from '../lib/poll';

type Item = Record<string, unknown>;
const sections = [
  ['medications', 'Medications', 'Amount per dose, timing and instructions'],
  ['tasks', 'Tasks', 'Daily activities and wound care'],
  ['appointments', 'Appointments', 'Follow-up dates and locations'],
  ['restrictions', 'Restrictions', 'Activities and limits stated in your document'],
  ['monitoring', 'Monitoring', 'What to watch and when to seek help'],
  ['warning_signs', 'Warning Signs', 'Symptoms and the action stated in your document'],
];
function record(value: unknown): Item {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Item : {};
}
function text(value: unknown): string {
  if (Array.isArray(value)) return value.map(text).filter(Boolean).join(', ');
  if (typeof value === 'string' || typeof value === 'number') return String(value);
  return '';
}
function Field({ label, value, required = false, prominent = false }: {
  label: string; value: unknown; required?: boolean; prominent?: boolean;
}) {
  const content = text(value);
  if (!content && !required) return null;
  return <div className={prominent ? 'field dose' : 'field'}>
    <dt>{label}</dt><dd className={!content ? 'missing' : undefined}>
      {content || 'Not specified in the document'}
    </dd>
  </div>;
}
function Card({ value, category }: { value: unknown; category: string }) {
  const item = record(value);
  const source = record(item.source);
  const heading = text(item.name || item.title || item.description || item.what || item.text || value) || 'Untitled item';
  const emergency = category === 'warning_signs' && item.urgency === 'emergency';
  return <article className={`item-card${emergency ? ' emergency' : ''}`}>
    <div className="card-heading"><h3>{heading}</h3>
      {item.needs_confirmation === true && <span className="badge review">Needs confirmation</span>}
      {emergency && <span className="badge urgent">Emergency</span>}
    </div>
    <dl className="fields">
      {category === 'medications' && <>
        <Field label="Strength" value={item.strength} />
        <Field label="Form" value={item.form} />
        <Field label="Amount per dose" value={item.dose} required prominent />
        <Field label="Times per day" value={item.times_per_day} />
        <Field label="When" value={item.time_of_day} />
        <Field label="As needed" value={item.as_needed === true ? 'Yes' : undefined} />
        <Field label="As-needed reason" value={item.as_needed_reason} />
        <Field label="Maximum administrations per day" value={item.max_per_day} />
        <Field label="Duration" value={item.duration_text} />
        <Field label="Instructions" value={item.instructions} />
        <Field label="Application site" value={item.site} />
      </>}
      {category === 'tasks' && <>
        <Field label="Details" value={item.details} />
        <Field label="Times per day" value={item.times_per_day} />
        <Field label="When" value={item.time_of_day} />
        <Field label="Clock times" value={item.clock_times} />
        <Field label="Duration" value={item.duration_text} />
      </>}
      {category === 'appointments' && <>
        <Field label="Date" value={item.date} required />
        <Field label="Time" value={item.time} />
        <Field label="Location" value={item.location} />
        <Field label="Conflicting dates — review required" value={item.conflicting_dates} />
      </>}
      {category === 'monitoring' && <>
        <Field label="How often" value={item.frequency_text} />
        <Field label="Concern threshold" value={item.threshold_text} />
      </>}
      {category === 'warning_signs' && <>
        <Field label="Action" value={item.action} required prominent />
        <Field label="Urgency" value={item.urgency === 'contact_care_team' ? 'Contact care team' : item.urgency} />
      </>}
    </dl>
    {text(item.status) && <p className="item-status">Tracking status: {text(item.status)}</p>}
    <details className="evidence"><summary>Source &amp; details</summary>
      {text(source.snippet) && <blockquote>{text(source.snippet)}</blockquote>}
      <dl className="fields">
        <Field label="Page" value={source.page} />
        <Field label="Document ID" value={source.document_id} />
        <Field label="Item ID" value={item.id} />
      </dl>
      {!text(source.snippet) && <p className="muted">No source snippet recorded.</p>}
    </details>
  </article>;
}
export default function RecoveryPlan({ state }: { state: RecoveryState }) {
  return <div className="recovery-plan">
    <div className="plan-header"><div><p className="eyebrow">Extracted document</p><h2>Recovery plan</h2></div>
      <span className="badge ready">{text(state.ingestion_status)}</span>
    </div>
    <p className="discharge">Discharge date: <strong>{text(state.discharge_date) || 'Not specified in the document'}</strong></p>
    <nav className="section-links" aria-label="Recovery plan sections">
      {sections.map(([key, title]) => <a key={key} href={`#${key}`}>{title}</a>)}
    </nav>
    {sections.map(([key, title, description]) => {
      const items = Array.isArray(state[key]) ? state[key] : [];
      return <section key={key} id={key} className="plan-section">
        <div className="section-title"><h2>{title}</h2><span className="count">{items.length}</span></div>
        <p className="muted section-description">{description}</p>
        {items.length ? <div className="card-grid">{items.map((item, index) =>
          <Card key={index} value={item} category={key} />)}</div> : <p className="empty">None recorded in the extraction.</p>}
      </section>;
    })}
    <details className="raw-json"><summary>Full RecoveryState JSON</summary><pre>{JSON.stringify(state, null, 2)}</pre></details>
  </div>;
}
