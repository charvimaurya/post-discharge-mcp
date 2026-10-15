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
import { daysAtHome, isObj, itemsMentioned, localTime, readChat, readPlan, readToday, reprompt, splitClock, str,
  type HelpAction, type PlanItem, type PlanSummary, type Source, type Today, type ToolCall } from '../../lib/assistant-data';
import { startReminderChecks } from '../../lib/reminder-check';
import { canListen, finishListening, listenOnce, speak } from '../../lib/voice';
import { alreadySpoken, clearSpoken, forgetSpoken, markSpoken, shouldSpeakOpening } from '../../lib/spoken';
import { BuildScreen, ConversationLog, LetterPanel, Screen, StartScreen, TodayPanel, ToolPanel, TopBar, VoicePanel, type Turn } from './parts';

type View = 'start' | 'build' | 'today';
const POLL_MS = 5000;
// How long the caption under a reminder stays on screen.
const REMINDER_NOTE_MS = 12000;
// The parts of the day the agent matches a report to (app/agent/occurrence_resolver.py).
const DAY_PARTS = ['morning', 'midday', 'afternoon', 'evening', 'bedtime'];

// Keep the mock-up's readable scale while extending the frame to every window edge.
function useFitFrame() {
  const [frame, setFrame] = useState({ scale: 1, width: 1280, height: 720 });
  useEffect(() => {
    const fit = () => {
      const scale = Math.min(window.innerWidth / 1280, window.innerHeight / 720);
      if (scale <= 0) return;
      setFrame({ scale, width: window.innerWidth / scale, height: window.innerHeight / scale });
    };
    fit(); window.addEventListener('resize', fit);
    return () => window.removeEventListener('resize', fit);
  }, []);
  return frame;
}

function sessionId(): string {
  let id = sessionStorage.getItem('afterward-session');
  if (!id) { id = `demo-${crypto.randomUUID()}`; sessionStorage.setItem('afterward-session', id); }
  return id;
}
// sessionStorage, or nothing when the browser blocks it.
function tabStore(): Storage | undefined {
  try { return window.sessionStorage; } catch { return undefined; }
}

// She has been greeted today: her next visit today opens with "Welcome back". Not worth an error.
function markGreeted() {
  void fetch('/api/greeted', { method: 'POST', cache: 'no-store' }).catch(() => undefined);
}

export default function DemoPage() {
  const frame = useFitFrame();
  const [view, setView] = useState<View>('start');
  const [error, setError] = useState('');

  // Upload and "building the plan"
  const [uploading, setUploading] = useState(false);
  const [buildStep, setBuildStep] = useState<1 | 2 | 3>(1);
  const [plan, setPlan] = useState<PlanSummary | null>(null);
  const [dischargeDate, setDischargeDate] = useState<string | null>(null);

  // Today and the conversation
  const [today, setToday] = useState<Today>({ clockLabel: '', firstName: null, openingGreeting: '', date: null, dischargeDate: null, items: [], pendingCheckin: null });
  const [todayLoaded, setTodayLoaded] = useState(false);
  const [openingCheckComplete, setOpeningCheckComplete] = useState(false);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [head, setHead] = useState('AfterWard');
  const [chips, setChips] = useState<{ kind: string; icon: string; text: string }[]>([]);
  const [calls, setCalls] = useState<ToolCall[]>([]);
  const [requestId, setRequestId] = useState<string | null>(null);  // the last chat turn's ID in the server logs
  const [source, setSource] = useState<Source>(null);
  // The "Get help" card: set by a symptom reply, cleared only when she taps "I'm feeling better".
  const [help, setHelp] = useState<HelpAction[] | null>(null);
  // After a reply about something else, the card shrinks to a one-line strip.
  const [helpCompact, setHelpCompact] = useState(false);
  // The plan items the last answer named: highlighted on the Today screen.
  const [focus, setFocus] = useState<string[]>([]);
  // When an answer names nothing in the plan: the next item, shown softly as "Next in your plan".
  const [nextHint, setNextHint] = useState<string | null>(null);
  // Shown when AfterWard speaks first: "Nobody set this reminder. It came from her letter."
  const [reminderNote, setReminderNote] = useState(false);
  const [justDone, setJustDone] = useState<PlanItem | null>(null);
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  // Her words so far while the microphone is on, shown as she speaks.
  const [hearing, setHearing] = useState('');
  const [speaking, setSpeaking] = useState(false);
  const [typing, setTyping] = useState(false);
  const [dev, setDev] = useState(false);
  const [micOk, setMicOk] = useState(false);
  // The id of the reminder currently shown on screen, or null.
  const shownCheckin = useRef<string | null>(null);
  const openingGreetingShown = useRef(false);
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
      setTodayLoaded(true);
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

  // Ask for a reminder check when the Today screen opens, then every 60 seconds, and read /today
  // straight after so a new reminder is shown and spoken at once. On AWS the EventBridge schedule
  // runs this check; locally the page asks for it. Same handler, same rules.
  useEffect(() => {
    if (view !== 'today') return;
    return startReminderChecks(
      async () => {
        const response = await fetch('/api/reminders/check', { method: 'POST', cache: 'no-store' });
        if (!response.ok) throw new Error('Reminder check failed.');
      },
      async () => {
        await loadToday();
        setOpeningCheckComplete(true);
      },
    );
  }, [view, loadToday]);

  // AfterWard speaks first. The demo reminder always has the same checkin_id, so "seen before" is
  // forgotten once /today reports no reminder: the next one with that id is shown and spoken again.
  useEffect(() => {
    // Only act on a real /today answer, not the empty starting state.
    if (view !== 'today' || !todayLoaded || !openingCheckComplete) return;
    const checkin = today.pendingCheckin;
    if (!checkin) {
      shownCheckin.current = null;
      clearSpoken(tabStore());
      if (!openingGreetingShown.current && today.openingGreeting) {
        openingGreetingShown.current = true;
        setHead('AfterWard');
        setTurns(t => [...t, { who: 'aw', text: today.openingGreeting }]);
        // After a reload the greeting is shown again, but not spoken twice.
        if (shouldSpeakOpening(tabStore(), today.openingGreeting)) void say(today.openingGreeting);
        markGreeted();
      }
      return;
    }
    // A pending reminder already includes a greeting, so do not add a second welcome.
    if (!openingGreetingShown.current) markGreeted();
    openingGreetingShown.current = true;
    if (checkin.id === shownCheckin.current) return;
    shownCheckin.current = checkin.id;
    const time = splitClock(today.clockLabel).time;
    setHead(`AfterWard speaks first${time ? ` · ${time}` : ''}`);
    setReminderNote(true);
    setTurns(t => [...t, { who: 'aw', text: checkin.text, reminder: true }]);
    setChips([]); setJustDone(null); setSource(null);
    // Survives a page reload, so a reminder still waiting is shown again but not spoken twice.
    if (!alreadySpoken(tabStore(), checkin.id)) {
      markSpoken(tabStore(), checkin.id);
      say(checkin.text);
    }
  }, [today.pendingCheckin, today.openingGreeting, today.clockLabel, todayLoaded, openingCheckComplete, view, say]);

  // The caption under a reminder stays for a while, then clears so the plan is not covered.
  useEffect(() => {
    if (!reminderNote) return;
    const timer = setTimeout(() => setReminderNote(false), REMINDER_NOTE_MS);
    return () => clearTimeout(timer);
  }, [reminderNote]);

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
    setBusy(true); setError(''); setChips([]); setJustDone(null); setReminderNote(false);
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
      setRequestId(reply.requestId);
      setSource(reply.source);
      if (reply.help) { setHelp(reply.help); setHelpCompact(false); } else setHelpCompact(true);
      const letterChip = reply.source
        ? [{ kind: '', icon: 'doc', text: `From your letter${reply.source.page ? `, page ${reply.source.page}` : ''}` }]
        : [];
      setChips(letterChip);
      // After the first reply to a reminder the header says "spoke first"; after that, just "AfterWard".
      setHead(h => (h.startsWith('AfterWard speaks first') ? h.replace('speaks', 'spoke') : 'AfterWard'));
      // The answer is shown and spoken at once. Refreshing the plan (ticks, highlights, the
      // "Saved" chip) follows alongside, instead of holding the answer back for it.
      setTurns(t => [...t, { who: 'aw', text: reply.text || 'Sorry, I could not answer that.' }]);
      setBusy(false);
      const speaking = say(reply.text);
      const after = await loadToday();
      const named = after ? itemsMentioned(reply.text, after.items) : [];
      setFocus(named);
      // Only for an answer that names no item, quotes no letter and is not about a symptom.
      setNextHint(after && !named.length && !reply.source && !reply.help && !reply.saved
        ? after.items.find(i => !i.done)?.id || null : null);
      // Only claim a save when a report_* tool really succeeded in this reply.
      const newlyDone = reply.saved ? after?.items.find(i => i.done && !before.has(i.id)) || null : null;
      setJustDone(newlyDone);
      if (newlyDone) {
        setChips([{ kind: 'ok', icon: 'check', text: `Saved to your plan${newlyDone.doneAt ? ` at ${localTime(newlyDone.doneAt)}` : ''}` }, ...letterChip]);
      }
      await speaking;
    } catch (e) {
      setError(e instanceof Error ? e.message : 'AfterWard could not answer just now.');
      setBusy(false);
    }
  }

  async function mic() {
    if (busy) return;
    // A second tap while listening means she has finished: send what was heard now.
    if (listening) { finishListening(); return; }
    window.speechSynthesis?.cancel();
    setListening(true);
    setHearing('');
    setError('');
    try {
      const heard = await listenOnce(setHearing);
      setListening(false);
      setHearing('');
      // Silence on screen looked like nothing was working; a lone short word is often not caught.
      if (heard) await send(heard);
      else {
        // Many people will have no screen: say it, and repeat the question still waiting, as Alexa re-prompts.
        setError('I didn’t catch that. Please try again with a few more words, tap an answer, or type.');
        void say(reprompt(turns));
      }
    } catch (e) {
      setListening(false);
      setHearing('');
      setError(e instanceof Error ? e.message : 'The microphone did not work. Please type instead.');
      setTyping(true);
    }
  }

  // Tapping "Mark as done" goes through AfterWard too, so the tick is a real report tool call.
  // An item that repeats in the day names its time of day ("my evening knee exercises"), so the
  // card that was tapped is the occurrence recorded, not just the next one due.
  const tapDone = (item: PlanItem) => {
    const slot = item.slot.toLowerCase();
    const part = item.repeat && DAY_PARTS.includes(slot) ? `${slot} ` : '';
    send(item.kind === 'medicine' ? `I've taken my ${part}${item.name.split(',')[0].toLowerCase()}.` : `I've done my ${part}${item.name.toLowerCase()}.`);
  };

  function openToday() {
    // Her click opens Today afresh, so the waiting reminder or greeting is spoken, even if this
    // tab has said it before.
    forgetSpoken(tabStore());
    shownCheckin.current = null;
    openingGreetingShown.current = false;
    setOpeningCheckComplete(false);
    setTodayLoaded(false);
    setView('today');
    // A click is needed before the browser lets the page speak. This click counts.
    window.speechSynthesis?.speak(new SpeechSynthesisUtterance(''));
  }

  function backToStart() {
    setTodayLoaded(false);
    setView('start');
  }

  const dayAtHome = daysAtHome(today.date, today.dischargeDate || dischargeDate);

  const reminderItemId = today.pendingCheckin?.itemId || null;
  const leftPanel = source
    ? <LetterPanel source={source} firstName={today.firstName} onBack={() => setSource(null)} help={help} onDismissHelp={() => setHelp(null)} />
    : <TodayPanel items={today.items} justDone={justDone} reminderItemId={reminderItemId} clock={today.clockLabel}
        dayAtHome={dayAtHome} firstName={today.firstName} compact={dev} busy={busy} onDone={tapDone}
        empty={todayLoaded && today.items.length === 0} onStart={backToStart}
        help={help} helpCompact={helpCompact} onDismissHelp={() => setHelp(null)} focus={focus} hint={nextHint} />;

  let screen;
  if (view === 'start') screen = <StartScreen onUpload={upload} onOpen={openToday} busy={uploading} />;
  else if (view === 'build') screen = <BuildScreen step={buildStep} plan={plan} onOpen={openToday} />;
  else screen = <Screen id="app">
    <TopBar clock={today.clockLabel} patient={today.firstName} dev={dev} onDev={() => setDev(d => !d)} />
    <div className="stage">
      {dev && <ConversationLog turns={turns} />}
      {leftPanel}
      {dev ? <ToolPanel calls={calls} requestId={requestId} />
        : <VoicePanel head={head} turns={turns} chips={chips} speaking={speaking} listening={listening} hearing={hearing} busy={busy}
            canListen={micOk} typing={typing} onMic={mic} onSend={send} onToggleTyping={() => setTyping(t => !t)} />}
    </div>
    {reminderNote && !dev && !source &&
      <div className="caption"><span>Nobody set this reminder. It came from her letter.</span></div>}
  </Screen>;

  return <div className="awapp"><div className="aw-viewport">
    <div className="aw-frame" style={{ width: frame.width, height: frame.height, transform: `scale(${frame.scale})` }}>
      {screen}
      {error && <div className="errline" role="alert">{error}</div>}
    </div>
  </div></div>;
}
