// Phase 15: the simulated Alexa+ screen, built to look like the mock-ups.
// Open http://127.0.0.1:3000/demo
//
// Where the data comes from (all through your existing server routes):
//   /api/upload, /api/recovery-state  -> start screen and "building the plan"
//   /api/today                        -> Today panel, clock, reminder (polled every 5 seconds)
//   /api/chat                         -> AfterWard's reply, tool calls, letter passage
'use client';
import '@fontsource/source-serif-4/400.css';
import '@fontsource/source-serif-4/600.css';
import '@fontsource/source-serif-4/400-italic.css';
import '@fontsource/ibm-plex-sans/400.css';
import '@fontsource/ibm-plex-sans/500.css';
import '@fontsource/ibm-plex-sans/600.css';
import '@fontsource/ibm-plex-sans/700.css';
import '@fontsource/ibm-plex-mono/400.css';
import '@fontsource/ibm-plex-mono/500.css';
import './afterward.css';
import { useCallback, useEffect, useRef, useState } from 'react';
import { waitForRecoveryState, type RecoveryState } from '../../lib/poll';
import { isObj, localTime, readChat, readPlan, readToday, splitClock, str,
  type PlanItem, type PlanSummary, type Source, type Today, type ToolCall } from '../../lib/assistant-data';
import { canListen, listenOnce, speak } from '../../lib/voice';
import { BuildScreen, ConversationLog, LetterPanel, Screen, StartScreen, TodayPanel, ToolPanel, TopBar, VoicePanel, type Turn } from './parts';

type View = 'start' | 'build' | 'today';
const POLL_MS = 5000;
const SPOKEN_KEY = 'afterward-spoken-checkins';

// Draws the 1280 x 720 screen and scales it to fill the window, so it matches the mock-ups.
function useFitScale() {
  const [scale, setScale] = useState(1);
  useEffect(() => {
    const fit = () => setScale(Math.min(window.innerWidth / 1280, window.innerHeight / 720));
    fit(); window.addEventListener('resize', fit);
    return () => window.removeEventListener('resize', fit);
  }, []);
  return scale;
}

function sessionId(): string {
  let id = sessionStorage.getItem('afterward-session');
  if (!id) { id = `demo-${crypto.randomUUID()}`; sessionStorage.setItem('afterward-session', id); }
  return id;
}
function alreadySpoken(id: string): boolean {
  try { return (JSON.parse(sessionStorage.getItem(SPOKEN_KEY) || '[]') as string[]).includes(id); } catch { return false; }
}
function markSpoken(id: string) {
  try {
    const ids = JSON.parse(sessionStorage.getItem(SPOKEN_KEY) || '[]') as string[];
    sessionStorage.setItem(SPOKEN_KEY, JSON.stringify([...ids, id]));
  } catch { /* storage blocked: it may be spoken again after a reload */ }
}

export default function DemoPage() {
  const scale = useFitScale();
  const [view, setView] = useState<View>('start');
  const [error, setError] = useState('');

  // Upload and "building the plan"
  const [uploading, setUploading] = useState(false);
  const [buildStep, setBuildStep] = useState<1 | 2 | 3>(1);
  const [plan, setPlan] = useState<PlanSummary | null>(null);
  const [dischargeDate, setDischargeDate] = useState<string | null>(null);

  // Today and the conversation
  const [today, setToday] = useState<Today>({ clockLabel: '', items: [], pendingCheckin: null });
  const [turns, setTurns] = useState<Turn[]>([]);
  const [head, setHead] = useState('AfterWard');
  const [chips, setChips] = useState<{ kind: string; icon: string; text: string }[]>([]);
  const [calls, setCalls] = useState<ToolCall[]>([]);
  const [source, setSource] = useState<Source>(null);
  const [justDone, setJustDone] = useState<PlanItem | null>(null);
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [typing, setTyping] = useState(false);
  const [dev, setDev] = useState(false);
  const [micOk, setMicOk] = useState(false);
  const todayRef = useRef(today);
  todayRef.current = today;

  useEffect(() => setMicOk(canListen()), []);

  const say = useCallback(async (text: string) => {
    setSpeaking(true);
    await speak(text);
    setSpeaking(false);
  }, []);

  const loadToday = useCallback(async (): Promise<Today | null> => {
    try {
      const response = await fetch('/api/today', { cache: 'no-store' });
      const data = await response.json();
      if (!response.ok) throw new Error(str(isObj(data) ? data.error : '') || 'Could not load today\'s plan.');
      const next = readToday(data);
      setToday(next);
      setError('');
      return next;
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load today\'s plan.');
      return null;
    }
  }, []);

  // Poll /api/today every 5 seconds while the Today screen is open. One read at a time.
  useEffect(() => {
    if (view !== 'today') return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      await loadToday();
      if (!stopped) timer = setTimeout(tick, POLL_MS);
    };
    tick();
    return () => { stopped = true; clearTimeout(timer); };
  }, [view, loadToday]);

  // AfterWard speaks first: show and speak a new reminder once.
  useEffect(() => {
    const checkin = today.pendingCheckin;
    if (view !== 'today' || !checkin || !checkin.text || alreadySpoken(checkin.id)) return;
    markSpoken(checkin.id);
    const time = splitClock(today.clockLabel).time;
    setHead(`AfterWard speaks first${time ? ` · ${time}` : ''}`);
    setTurns(t => [...t, { who: 'aw', text: checkin.text, reminder: true }]);
    setChips([]); setJustDone(null); setSource(null);
    say(checkin.text);
  }, [today.pendingCheckin, today.clockLabel, view, say]);

  // ---------- Upload ----------
  async function upload(file: File) {
    setUploading(true); setError('');
    try {
      const form = new FormData(); form.set('file', file);
      const response = await fetch('/api/upload', { method: 'POST', body: form });
      const uploaded = await response.json();
      if (!response.ok) throw new Error(uploaded.error || 'Upload failed.');
      setView('build'); setBuildStep(2); setPlan(null);
      const state: RecoveryState = await waitForRecoveryState(uploaded.document_id, async signal => {
        const r = await fetch(`/api/recovery-state?patient_id=${encodeURIComponent(uploaded.patient_id)}`, { signal, cache: 'no-store' });
        const data = await r.json();
        if (!r.ok) throw new Error(data.error || 'Could not check the plan.');
        return data;
      }, new AbortController().signal);
      setPlan(readPlan(state));
      setDischargeDate(str(state.discharge_date) || null);
      setBuildStep(3);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Upload failed.');
      setView('start');
    } finally {
      setUploading(false);
    }
  }

  // ---------- Talking to AfterWard ----------
  async function send(message: string) {
    if (busy || !message.trim()) return;
    window.speechSynthesis?.cancel();
    setBusy(true); setError(''); setChips([]); setJustDone(null);
    setTurns(t => [...t, { who: 'you', text: message }]);
    const before = new Set(todayRef.current.items.filter(i => i.done).map(i => i.id));
    try {
      const response = await fetch('/api/chat', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, session_id: sessionId() }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(str(isObj(data) ? data.error : '') || 'AfterWard could not answer just now.');
      const reply = readChat(data);
      setCalls(c => [...c, ...reply.tools]);
      setSource(reply.source);
      const after = await loadToday();
      const newlyDone = after?.items.find(i => i.done && !before.has(i.id)) || null;
      setJustDone(newlyDone);
      const nextChips: typeof chips = [];
      if (newlyDone) nextChips.push({ kind: 'ok', icon: 'check', text: `Saved to your plan${newlyDone.doneAt ? ` at ${localTime(newlyDone.doneAt)}` : ''}` });
      if (reply.source) nextChips.push({ kind: '', icon: 'doc', text: `From your letter${reply.source.page ? `, page ${reply.source.page}` : ''}` });
      setChips(nextChips);
      // After the first reply to a reminder the header says "spoke first"; after that, just "AfterWard".
      setHead(h => (h.startsWith('AfterWard speaks first') ? h.replace('speaks', 'spoke') : 'AfterWard'));
      setTurns(t => [...t, { who: 'aw', text: reply.text || 'Sorry, I could not answer that.' }]);
      setBusy(false);
      await say(reply.text);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'AfterWard could not answer just now.');
      setBusy(false);
    }
  }

  async function mic() {
    if (busy || listening) return;
    window.speechSynthesis?.cancel();
    setListening(true);
    try {
      const heard = await listenOnce();
      setListening(false);
      if (heard) await send(heard);
    } catch (e) {
      setListening(false);
      setError(e instanceof Error ? e.message : 'The microphone did not work. Please type instead.');
      setTyping(true);
    }
  }

  // Tapping Done goes through AfterWard too, so the tick is a real report tool call.
  const tapDone = (item: PlanItem) =>
    send(item.kind === 'medicine' ? `I've taken my ${item.name.split(',')[0].toLowerCase()}.` : `I've done my ${item.name.toLowerCase()}.`);

  function openToday() {
    setView('today');
    // A click is needed before the browser lets the page speak. This click counts.
    window.speechSynthesis?.speak(new SpeechSynthesisUtterance(''));
  }

  const dayAtHome = (() => {
    if (!dischargeDate) return null;
    const d = new Date(`${dischargeDate}T12:00:00`);
    const now = new Date(`${splitClock(today.clockLabel).day} ${new Date().getFullYear()} 12:00`);
    const days = Math.round((now.getTime() - d.getTime()) / 86_400_000);
    return days > 0 && days < 365 ? days : null;
  })();

  const reminderItemId = today.pendingCheckin?.itemId || null;
  const leftPanel = source && !dev
    ? <LetterPanel source={source} onBack={() => setSource(null)} />
    : <TodayPanel items={today.items} justDone={justDone} reminderItemId={reminderItemId} clock={today.clockLabel}
        dayAtHome={dayAtHome} compact={dev} busy={busy} onDone={tapDone} />;

  let screen;
  if (view === 'start') screen = <StartScreen onUpload={upload} onOpen={openToday} busy={uploading} />;
  else if (view === 'build') screen = <BuildScreen step={buildStep} plan={plan} onOpen={openToday} />;
  else screen = <Screen id="app">
    <TopBar clock={today.clockLabel} dev={dev} onDev={() => setDev(d => !d)} />
    <div className="stage">
      {dev && <ConversationLog turns={turns} />}
      {leftPanel}
      {dev ? <ToolPanel calls={calls} />
        : <VoicePanel head={head} turns={turns} chips={chips} speaking={speaking} listening={listening} busy={busy}
            canListen={micOk} typing={typing} onMic={mic} onSend={send} onToggleTyping={() => setTyping(t => !t)} />}
    </div>
  </Screen>;

  return <div className="awapp"><div className="aw-viewport">
    <div style={{ width: 1280, height: 720, transform: `scale(${scale})`, flex: 'none', position: 'relative' }}>
      {screen}
      {error && <div className="errline" role="alert">{error}</div>}
    </div>
  </div></div>;
}
