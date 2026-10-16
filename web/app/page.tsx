// Local PDF upload and inspection of the resulting RecoveryState.
'use client';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { waitForRecoveryState, type RecoveryState } from '../lib/poll';
import RecoveryPlan from './recovery-plan';

export default function Page() {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState('Choose a PDF to begin.');
  const [error, setError] = useState('');
  const [documentId, setDocumentId] = useState('');
  const [state, setState] = useState<RecoveryState | null>(null);
  const active = useRef<AbortController | null>(null);
  useEffect(() => () => active.current?.abort(), []);

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file || busy) return;
    active.current?.abort();
    const controller = new AbortController();
    active.current = controller;
    setBusy(true); setError(''); setState(null); setDocumentId(''); setStatus('Uploading...');
    try {
      const form = new FormData(); form.set('file', file);
      const response = await fetch('/api/upload', { method: 'POST', body: form, signal: controller.signal });
      const uploaded = await response.json();
      if (!response.ok) throw new Error(uploaded.error || 'Upload failed.');
      setDocumentId(uploaded.document_id);
      setStatus('Processing document...');
      const result = await waitForRecoveryState(uploaded.document_id, async signal => {
        const response = await fetch(`/api/recovery-state?patient_id=${encodeURIComponent(uploaded.patient_id)}`, {
          signal, cache: 'no-store',
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Polling failed.');
        return data;
      }, controller.signal);
      setState(result); setStatus('Ready');
    } catch (error) {
      if (!controller.signal.aborted) {
        setError(error instanceof Error ? error.message : 'Request failed.'); setStatus('Failed');
      }
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }

  return <main>
    <header className="page-header">
      <p className="eyebrow">AfterWard</p>
      <h1>Your discharge document,<br />clearly organised.</h1>
      <p className="intro">Upload a PDF to see its medications, care instructions and follow-up plan.</p>
    </header>
    <section className="upload-panel" aria-labelledby="upload-title">
      <h2 id="upload-title">Upload a discharge PDF</h2>
      <form onSubmit={upload}>
        <div className="file-picker"><label htmlFor="pdf">Choose your document</label>
          <input id="pdf" type="file" accept=".pdf,application/pdf" disabled={busy}
            onChange={event => setFile(event.target.files?.[0] || null)} />
        </div>
        <button disabled={!file || busy} type="submit">{busy ? 'Please wait…' : 'Upload'}</button>
      </form>
      <div className={`upload-status${state ? ' success' : ''}`} role="status" aria-live="polite">
        <span className="status-dot" aria-hidden="true" />{status}
      </div>
      {documentId && <p className="document-id">Document ID: <code>{documentId}</code></p>}
      {error && <p role="alert" className="error">{error}</p>}
    </section>
    {state && <RecoveryPlan state={state} />}
  </main>;
}
