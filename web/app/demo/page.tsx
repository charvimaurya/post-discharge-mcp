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
import { WeekPanel } from './week-panel';
import { readWeekSummary, type WeekSummary } from '../../lib/week-summary';
import { completionFingerprint, readSequence } from '../../lib/recovery-sync';
import { useCallback, useEffect, useRef, useState } from 'react';
import { waitForRecoveryState, type RecoveryState } from '../../lib/poll';
import { daysAtHome, isObj, itemsMentioned, localTime, readChat, readPlan, readToday, reprompt, splitClock, str, wasReset,
  type ChatReply, type HelpAction, type PlanItem, type PlanSummary, type Source, type Today, type ToolCall } from '../../lib/assistant-data';
import { startReminderChecks } from '../../lib/reminder-check';
import { addTurn, feedBubbles, feedReply, speakable, startAlexaFeed } from '../../lib/alexa-feed';
import { replyView } from '../../lib/reply-view';
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
  const [today, setToday] = useState<Today>({ clockLabel: '', firstName: null, openingGreeting: '', date: null, dischargeDate: null, items: [], pendingCheckin: null, resetAt: null });
  const [todayLoaded, setTodayLoaded] = useState(false);
  const [week, setWeek] = useState<WeekSummary | null>(null);
  const [weekLoading, setWeekLoading] = useState(false);
  const [weekError, setWeekError] = useState(false);
  const weekRequest = useRef(0);
  const loadWeek = useCallback(async () => {
    const sequence = ++weekRequest.current;
    setWeekLoading(true);
    setWeek(null);
    setWeekError(false);
    try {
      const response = await fetch('/api/week-summary', { cache: 'no-store' });
      if (!response.ok) throw new Error('Weekly history unavailable');
      const next = readWeekSummary(await response.json());
      if (!next) throw new Error('Invalid weekly history');
      if (sequence === weekRequest.current) setWeek(next);
    } catch {
      if (sequence === weekRequest.current) setWeekError(true);
    } finally {
      if (sequence === weekRequest.current) setWeekLoading(false);
    }
  }, []);

  const completionVersion = completionFingerprint(today);
  useEffect(() => {
    if (view !== 'today' || !today.date) return;
    void loadWeek();
    return () => { weekRequest.current += 1; };
  }, [view, today.date, completionVersion, loadWeek]);
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
  const [resetting, setResetting] = useState(false);
  const [micOk, setMicOk] = useState(false);
  // The id of the reminder currently shown on screen, or null.
  const shownCheckin = useRef<string | null>(null);
  const openingGreetingShown = useRef(false);
  const todayRef = useRef(today);
  todayRef.current = today;
  // The conversation as last drawn: the Alexa feed checks the latest message before adding a greeting.
  const turnsRef = useRef(turns);
  turnsRef.current = turns;
  // The last reset time /today reported; undefined until the first read.
  const seenResetAt = useRef<string | null | undefined>(undefined);
  // Bumped after a reset, so the greeting effect runs again even if /today looks the same.
  const [resets, setResets] = useState(0);

  useEffect(() => setMicOk(canListen()), []);

  const say = useCallback(async (text: string) => {
    setSpeaking(true);
    await speak(text);
    setSpeaking(false);
  }, []);

  // Empty the chat panel (web and "via Alexa" bubbles) and everything that hangs off the last reply.
  // withGreeting: let the greeting (or a waiting reminder) be shown again from the next /today.
  const clearChat = useCallback((withGreeting: boolean) => {
    turnsRef.current = [];
    setTurns([]); setCalls([]); setChips([]); setRequestId(null); setSource(null);
    setHelp(null); setHelpCompact(false); setFocus([]); setNextHint(null);
    setJustDone(null); setReminderNote(false); setHead('AfterWard');
    shownCheckin.current = null;
    if (withGreeting) {
      openingGreetingShown.current = false;
      setResets(n => n + 1);
    }
  }, []);

  const todayReads = useRef(readSequence());
  const loadToday = useCallback(async (): Promise<Today | null> => {
    const request = todayReads.current.begin();
    try {
      const response = await fetch('/api/today', { cache: 'no-store' });
      const data = await response.json();
      if (!response.ok) throw new Error(str(isObj(data) ? data.error : '') || 'Could not load today\'s plan.');
      const next = readToday(data);
      if (!todayReads.current.current(request)) return null;
      // Reset elsewhere (the script, the button, or after a long idle): start the chat afresh.
      // Only a newer time counts: a slow read from before the reset must not clear the chat again.
      if (wasReset(seenResetAt.current, next.resetAt)) clearChat(true);
      if (seenResetAt.current === undefined || wasReset(seenResetAt.current, next.resetAt)) seenResetAt.current = next.resetAt;
      setToday(next);
      setTodayLoaded(true);
      setError('');
      return next;
    } catch (e) {
      if (!todayReads.current.current(request)) return null;
      setError(e instanceof Error ? e.message : 'Could not load today\'s plan.');
      return null;
    }
  }, [clearChat]);

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
        setTurns(t => addTurn(t, { who: 'aw', text: today.openingGreeting }));
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
    setTurns(t => addTurn(t, { who: 'aw', text: checkin.text, reminder: true }));
    setChips([]); setJustDone(null); setSource(null);
    // Survives a page reload, so a reminder still waiting is shown again but not spoken twice.
    if (!alreadySpoken(tabStore(), checkin.id)) {
      markSpoken(tabStore(), checkin.id);
      say(checkin.text);
    }
  }, [today.pendingCheckin, today.openingGreeting, today.clockLabel, todayLoaded, openingCheckComplete, view, say, resets]);

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
      const form = new FormData(); form.set('file', file); form.set('session_id', sessionId());
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

  // ---------- Reset demo ----------
  // Resets the demo patient on the server (today's completions and any waiting reminder) and
  // forgets this session's conversation there. The panel clears at once; the next /today sees the
  // new reset time and shows only the greeting.
  async function resetDemo() {
    if (resetting || busy) return;
    window.speechSynthesis?.cancel();
    setResetting(true); setError('');
    // Not the greeting yet: that waits for the reset plan, so the old one does not flash up.
    clearChat(false);
    try {
      const response = await fetch('/api/reset', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, cache: 'no-store',
        body: JSON.stringify({ session_id: sessionId() }),
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(result.error || 'Could not reset the demo.');
      await loadToday();
      await loadWeek();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not reset the demo.');
    } finally {
      setResetting(false);
    }
  }

  // ---------- Talking to AfterWard ----------
  // One reply on screen: the same for the web chat and for a reply via Alexa (letter excerpt,
  // "Feeling unwell?" card, chips, ticks). Only a web reply is spoken (lib/reply-view.ts).
  // before: the items already done before she spoke, to find what this reply saved.
  const showReply = useCallback(async (reply: ChatReply, before: Set<string>, via?: 'alexa') => {
    const view = replyView(reply, via);
    setCalls(c => [...c, ...reply.tools]);
    setRequestId(reply.requestId);
    setSource(view.source);
    if (view.help) { setHelp(view.help); setHelpCompact(false); } else setHelpCompact(true);
    setChips(view.chips);
    // After the first reply to a reminder the header says "spoke first"; after that, just "AfterWard".
    setHead(h => (h.startsWith('AfterWard speaks first') ? h.replace('speaks', 'spoke') : 'AfterWard'));
    // The answer is shown and spoken at once. Refreshing the plan (ticks, highlights, the
    // "Saved" chip) follows alongside, instead of holding the answer back for it.
    setTurns(t => addTurn(t, view.turn));
    const speaking = view.speak ? say(reply.text) : Promise.resolve();
    // Over the demo limit nothing changed, so Today is not reloaded (that would call MCP tools).
    if (reply.rateLimited) { await speaking; return; }
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
      setChips([{ kind: 'ok', icon: 'check', text: `Saved to your plan${newlyDone.doneAt ? ` at ${localTime(newlyDone.doneAt)}` : ''}` }, ...view.chips]);
    }
    await speaking;
  }, [say, loadToday]);

  // What she says to the Echo, and the reply, shown in the chat panel as "via Alexa" (every 2 seconds,
  // only turns after the page opened, paused while the tab is hidden). The left panel and the help
  // card react as for a web reply, but nothing is spoken here. Off or failing: nothing is shown.
  useEffect(() => {
    if (view !== 'today') return;
    return startAlexaFeed({
      fetchFeed: async after => {
        const response = await fetch(`/api/conversation${after === null ? '' : `?after=${after}`}`, { cache: 'no-store' });
        if (!response.ok) throw new Error('No Alexa feed.');
        return response.json();
      },
      onEntries: entries => {
        let latest: Turn | undefined = turnsRef.current[turnsRef.current.length - 1];
        for (const entry of entries) {
          const show = feedBubbles(entry, latest);
          if (!show.said && !show.reply) continue;
          const before = new Set(todayRef.current.items.filter(i => i.done).map(i => i.id));
          setChips([]); setJustDone(null); setReminderNote(false);
          if (show.said) setTurns(t => [...t, { who: 'you', text: entry.said, via: 'alexa' }]);
          void showReply(feedReply(entry), before, 'alexa');
          latest = { who: 'aw', text: entry.reply, via: 'alexa' };
        }
      },
      page: document,
    });
  }, [view, showReply]);

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
      setBusy(false);
      await showReply(readChat(data), before);
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
        void say(reprompt(turns.filter(speakable)));
      }
    } catch (e) {
      setListening(false);
      setHearing('');
      setError(e instanceof Error ? e.message : 'The microphone did not work. Please type instead.');
      setTyping(true);
    }
  }

  // Task cards retain the selected occurrence ID. Medicine reports keep the agent's safety checks.
  const tapDone = async (item: PlanItem) => {
    const slot = item.slot.toLowerCase();
    const part = item.repeat && DAY_PARTS.includes(slot) ? `${slot} ` : '';
    if (item.kind === 'medicine') {
      await send(`I've taken my ${part}${item.name.split(',')[0].toLowerCase()}.`);
      return;
    }
    if (busy || item.done) return;
    setBusy(true); setError(''); setChips([]); setJustDone(null); setReminderNote(false);
    const before = new Set(todayRef.current.items.filter(i => i.done).map(i => i.id));
    setTurns(t => [...t, { who: 'you', text: `I've done my ${part}${item.name.toLowerCase()}.` }]);
    try {
      const response = await fetch('/api/tasks/complete', { method: 'POST',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ occurrence_id: item.id }) });
      const data = await response.json();
      if (!response.ok) throw new Error(str(isObj(data) ? data.error : '') || 'Could not save that task.');
      await showReply(readChat(data), before);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save that task.');
    } finally { setBusy(false); }
  };

  function openToday() {
    // Her click opens Today afresh, so the waiting reminder or greeting is spoken, even if this
    // tab has said it before.
    forgetSpoken(tabStore());
    shownCheckin.current = null;
    // The greeting comes once per page load or reset: coming back to Today with the chat
    // already on screen does not add another.
    if (!turnsRef.current.length) openingGreetingShown.current = false;
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
        help={help} helpCompact={helpCompact} onDismissHelp={() => setHelp(null)} focus={focus} hint={nextHint}
        weekly={<WeekPanel summary={week} loading={weekLoading} error={weekError} onRefresh={() => void loadWeek()} />} />;

  let screen;
  if (view === 'start') screen = <StartScreen onUpload={upload} onOpen={openToday} busy={uploading} />;
  else if (view === 'build') screen = <BuildScreen step={buildStep} plan={plan} onOpen={openToday} />;
  else screen = <Screen id="app">
    <TopBar clock={today.clockLabel} patient={today.firstName} dev={dev} onDev={() => setDev(d => !d)}
      onReset={resetDemo} resetting={resetting} />
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
