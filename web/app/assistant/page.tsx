// Simulated Alexa+ client: speaks a waiting reminder first, then chats with AfterWard.
'use client';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import {
  loadSpokenId, planCheckin, saveSpokenId, startPolling,
  type PendingCheckin, type TodayResponse,
} from '../../lib/checkin';
import { speak, unlockSpeech } from '../../lib/speech';

type Bubble = { key: string; from: 'afterward' | 'patient'; text: string; label?: string };

function sessionStore(): Storage | undefined {
  try { return window.sessionStorage; } catch { return undefined; }
}

export default function Assistant() {
  const [started, setStarted] = useState(false);
  const [bubbles, setBubbles] = useState<Bubble[]>([]);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  // Refs, so the polling callback always sees current values.
  const startedRef = useRef(false);
  const shownId = useRef<string | null>(null);
  const spokenId = useRef<string | null>(null);
  const latest = useRef<PendingCheckin | null>(null);
  const sessionId = useRef<string | undefined>(undefined);
  const counter = useRef(0);

  function add(bubble: Omit<Bubble, 'key'>) {
    const key = `b${counter.current++}`;
    setBubbles(current => [...current, { ...bubble, key }]);
  }

  function handleCheckin(pending: PendingCheckin | null) {
    latest.current = pending;
    const plan = planCheckin(pending, {
      shownId: shownId.current, spokenId: spokenId.current, started: startedRef.current,
    });
    if (!pending) return;
    if (plan.show) {
      shownId.current = pending.checkin_id;
      add({ from: 'afterward', label: 'AfterWard speaks first', text: pending.text });
    }
    if (plan.speak) {
      spokenId.current = pending.checkin_id;
      saveSpokenId(sessionStore(), pending.checkin_id);
      speak(pending.text);
    }
  }

  useEffect(() => {
    spokenId.current = loadSpokenId(sessionStore());
    return startPolling<TodayResponse>(
      async signal => {
        const response = await fetch('/api/today', { signal, cache: 'no-store' });
        const body = await response.json();
        if (!response.ok) throw new Error(body.error || 'Could not check for reminders.');
        return body;
      },
      today => { setError(''); handleCheckin(today.pending_checkin ?? null); },
      failure => setError(failure instanceof Error ? failure.message : 'Could not check for reminders.'),
    );
  }, []);

  function start() {
    unlockSpeech();
    startedRef.current = true;
    setStarted(true);
    // A reminder shown before Start is spoken now.
    handleCheckin(latest.current);
  }

  async function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = message.trim();
    if (!text || busy) return;
    setBusy(true); setError(''); setMessage('');
    add({ from: 'patient', text });
    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, session_id: sessionId.current }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error || 'The assistant did not reply.');
      sessionId.current = body.session_id;
      add({ from: 'afterward', text: body.response });
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'The assistant did not reply.');
    } finally {
      setBusy(false);
    }
  }

  return <main>
    <header className="page-header">
      <p className="eyebrow">AfterWard · Simulated Alexa+</p>
      <h1>AfterWard assistant</h1>
    </header>
    {!started && <section className="upload-panel">
      <p className="intro">Press Start to let AfterWard speak.</p>
      <button type="button" onClick={start}>Start</button>
    </section>}
    <section className="chat" aria-live="polite">
      {bubbles.map(bubble => <div key={bubble.key} className={`bubble ${bubble.from}`}>
        {bubble.label && <p className="bubble-label">{bubble.label}</p>}
        <p>{bubble.text}</p>
      </div>)}
    </section>
    <form onSubmit={send}>
      <input aria-label="Message" value={message} disabled={busy}
        onChange={event => setMessage(event.target.value)} placeholder="Say something to AfterWard" />
      <button type="submit" disabled={busy || !message.trim()}>{busy ? 'Please wait…' : 'Send'}</button>
    </form>
    {error && <p role="alert" className="error">{error}</p>}
  </main>;
}
