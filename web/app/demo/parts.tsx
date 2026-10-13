// The building blocks of the demo screen. Each one copies a part of the mock-ups
// (docs/ui_mockups/source/screens.py) and uses the same CSS class names.
import { useEffect, useRef, type FormEvent, type ReactNode } from 'react';
import { Icon, Logo } from './icons';
import { letterBlocks, localTime, prettyTime, slotOrder, splitClock, type LetterBlock, type HelpAction, type PlanItem, type PlanSummary, type Source, type ToolCall } from '../../lib/assistant-data';

// ---------- Frame: top bar and footer ----------

export function TopBar({ clock, dev, onDev }: { clock?: string; dev?: boolean; onDev?: () => void }) {
  const { day, time } = splitClock(clock || '');
  return <header className="top">
    <Logo /><span className="name">AfterWard</span>
    {clock && <span className="clock">{day} &nbsp;<b>{time}</b></span>}
    <span className="spacer" />
    {onDev && <button type="button" className={`dev${dev ? ' on' : ''}`} onClick={onDev} aria-pressed={dev}>Developer view <i /></button>}
    <span className="sim">Simulated Alexa+</span>
  </header>;
}

export function Footer() {
  return <footer className="footbar">
    <span>AfterWard · A living recovery plan for Alexa+</span>
    <span>Synthetic patient data · Simulated Alexa+</span>
  </footer>;
}

export function Screen({ id, dark, children }: { id: string; dark?: boolean; children: ReactNode }) {
  return <section className={`screen${dark ? ' dark' : ''}`} id={id}>{children}<Footer /></section>;
}

// ---------- Start screen (mock-up 00_start) ----------

export function StartScreen({ onUpload, onOpen, busy }: { onUpload: (file: File) => void; onOpen: () => void; busy: boolean }) {
  return <Screen id="s00" dark>
    <div className="glow" /><div className="sun" />
    <TopBar />
    <div className="centre" style={{ gap: 16, height: 560, position: 'relative' }}>
      <div className="eyebrow rose">A living recovery plan for Alexa+</div>
      <h2 style={{ fontSize: 58, lineHeight: 1.08, maxWidth: 960 }}>Discharge is one moment.<br />Recovery happens every day.</h2>
      <p className="vision">No one should have to remember their recovery alone.</p>
      <p className="lead" style={{ fontSize: 18, maxWidth: 640, lineHeight: 1.45 }}>
        Signed in as Margaret Ellis, a synthetic demo patient. Upload a discharge letter to build today&apos;s plan.</p>
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 14, marginTop: 8 }}>
        <label className="btn primary" style={{ cursor: busy ? 'default' : 'pointer' }}>
          <Icon name="upload" size={22} stroke={2.2} />{busy ? 'Uploading…' : 'Upload a discharge letter'}
          <input type="file" accept=".pdf,application/pdf" hidden disabled={busy}
            onChange={e => { const f = e.target.files?.[0]; if (f) onUpload(f); e.target.value = ''; }} />
        </label>
        <button type="button" className="textlink" onClick={onOpen}>
          Already uploaded your letter? <b>Open today&apos;s plan</b><Icon name="arrow" size={18} stroke={2} /></button>
      </div>
      <div className="how"><div><b>1</b>Upload the letter once</div><div><b>2</b>AfterWard checks every line</div>
        <div><b>3</b>A plan, reminders and answers each day</div></div>
    </div>
  </Screen>;
}

// ---------- Building the plan (mock-ups 03 and 01) ----------

export function BuildScreen({ step, plan, onOpen }: { step: 1 | 2 | 3; plan: PlanSummary | null; onOpen: () => void }) {
  const cls = (n: number) => (step > n ? 'is-done' : step === n ? 'is-now' : '');
  const sections = ['Medicines', 'Each day', 'Appointments'] as const;
  const icons = { Medicines: 'pill', 'Each day': 'walk', Appointments: 'calendar' };
  // "Each day" lists the tasks with a set time or count, so the appointments stay in view.
  const rowsFor = (section: string) => {
    const all = (plan?.rows || []).filter(r => r.section === section);
    const timed = all.filter(r => r.when);
    return (section === 'Each day' && timed.length ? timed : all).slice(0, 4);
  };
  const lines = [100, 84, 92, 100, 76, 90, 96, 70].map((w, i) => <div key={i} className="ln" style={{ width: `${w}%` }} />);
  return <Screen id="s01">
    <TopBar />
    <div className="stage">
      <div className="panel letterside">
        <div className="eyebrow" style={{ marginBottom: 10 }}>Her discharge letter</div>
        <div className="paper sm"><div className="banner">Synthetic document · Not a real patient</div>
          <div className="in letterlist">
            <h4>Discharge letter and recovery instructions</h4>
            <h5>Your medicines</h5>
            {plan ? plan.quotes.slice(0, 4).map((q, i) => <div key={i} className={q.flagged ? 'hl' : 'txt'}>{q.text}</div>) : lines}
            {plan && plan.taskQuotes.length > 0 && <>
              <h5>Each day at home</h5>
              {plan.taskQuotes.slice(0, 2).map((q, i) => <div key={i} className="txt">{q}</div>)}
            </>}
          </div></div>
        {/* Progress while the letter is read; the finished screen shows the caption instead. */}
        {step < 3 && <div className="steps">
          <b className={cls(1)}>{step > 1 && <Icon name="check" size={16} stroke={2.6} />}Read the letter</b><i />
          <b className={cls(2)}>Check every line</b><i />
          <b className={cls(3)}>Plan ready</b>
        </div>}
      </div>
      <div className="joinslot"><span className="join"><Icon name="arrow" size={22} stroke={2.2} /></span></div>
      <div className="panel grow">
        <div className="eyebrow rose">The plan AfterWard built</div>
        <div className="planrows">
          {sections.map(s => <div key={s}>
            <div className="sec"><Icon name={icons[s]} size={18} stroke={2} />{s}</div>
            {plan ? rowsFor(s).map((r, i) =>
              <div key={i} className="row"><span>{r.text}{r.flag && <> <span className="chip amber">{r.flag}</span></>}</span>
                <span className="when">{r.when}</span></div>)
              : <><div className="skeleton" style={{ width: '64%' }} /><div className="skeleton" style={{ width: '50%' }} /></>}
          </div>)}
        </div>
        {plan && <div className="planfoot">
          <span className="chip grey"><Icon name="stop" size={15} stroke={2} />{plan.mustNot} things you must not do</span>
          <span className="chip grey"><Icon name="alert" size={15} stroke={2} />{plan.warnings} warning signs</span>
          {plan.careNotes > 0 && <span className="chip grey">{plan.careNotes} care notes</span>}
          {step === 3 && <button type="button" className="btn primary openplan" onClick={onOpen}>Open today&apos;s plan<Icon name="arrow" size={18} stroke={2.2} /></button>}
        </div>}
      </div>
    </div>
    {step === 3 && <div className="caption"><span>Built from her discharge letter. Nobody typed this in.</span></div>}
  </Screen>;
}

// ---------- Today panel (mock-ups 02 and 04) ----------

function Ring({ done, total }: { done: number; total: number }) {
  const len = 2 * Math.PI * 23;
  return <div className="ring">
    <div className="n"><b>{done} of {total}</b>done today</div>
    <svg width="58" height="58" viewBox="0 0 58 58" aria-hidden="true">
      <circle cx="29" cy="29" r="23" fill="none" stroke="#EFE8DC" strokeWidth="7" />
      {done > 0 && <circle cx="29" cy="29" r="23" fill="none" stroke="#1F5E8C" strokeWidth="7" strokeLinecap="round"
        strokeDasharray={`${((len * done) / Math.max(total, 1)).toFixed(1)} ${len.toFixed(1)}`} transform="rotate(-90 29 29)" />}
    </svg>
  </div>;
}

const repeatText = (i: PlanItem) => (i.repeat ? `, ${i.repeat.index} of ${i.repeat.total}` : '');

function Card({ item, due, onDone, busy }: { item: PlanItem; due: string | null; onDone?: (i: PlanItem) => void; busy?: boolean }) {
  const state = item.done ? ' ok' : due ? ' due' : '';
  return <div className={`item${state}`}>
    <span className="ico">{item.done ? <Icon name="check" size={26} stroke={2.4} /> : <Icon name={item.kind === 'medicine' ? 'pill' : /walk/i.test(item.name) ? 'walk' : 'exercise'} size={27} />}</span>
    <div className="t">
      <b>{item.title}{repeatText(item)}
        {item.repeat && <span className="dots">{Array.from({ length: item.repeat.total }, (_, n) =>
          <i key={n} className={n < item.repeat!.doneInGroup ? 'on' : ''} />)}</span>}</b>
      <span className="d">{item.detail}
        {due && <> <span className="chip rose"><Icon name="bell" size={15} stroke={2} />{due}</span></>}
        {item.needsConfirmation && <> <span className="chip amber">{item.confirmationText || 'Needs confirmation'}</span></>}</span>
      {item.quote && <span className="src" title={item.quote}><em>Your letter{item.page ? `, page ${item.page}` : ''}</em>&ldquo;{item.quote}&rdquo;</span>}
    </div>
    {item.done
      ? <span className="done-at"><Icon name="check" size={22} stroke={2.4} />Done{item.doneAt ? ` at ${localTime(item.doneAt)}` : ''}</span>
      : onDone && <button type="button" className="btn-done" disabled={busy} onClick={() => onDone(item)}>
          <Icon name="ring" size={20} stroke={2.2} />Mark as done</button>}
  </div>;
}

// Minutes from the clock label time to the item's clock time, as "Due in 30 minutes".
function dueText(item: PlanItem, clock: string): string | null {
  const now = /(\d{1,2}):(\d{2})/.exec(clock);
  const at = /(\d{1,2}):(\d{2})/.exec(item.clockTime || '');
  if (!now || !at) return 'Reminder sent';
  const mins = (+at[1] * 60 + +at[2]) - (+now[1] * 60 + +now[2]);
  return mins > 0 ? `Due in ${mins} minutes` : 'Due now';
}

// ---------- "Get help" card: shown on top of Today after she says she feels unwell ----------
// The 999 and NHS 111 lines are the same fixed wording AfterWard speaks (app/agent/symptoms.py).
// "Your letter says" lines are the letter's own actions, never invented.
export function HelpCard({ actions, onDismiss }: { actions: HelpAction[]; onDismiss: () => void }) {
  return <section className="helpcard" role="alert" aria-label="Getting help">
    <div className="help-head"><span className="help-ico"><Icon name="alert" size={22} stroke={2.2} /></span>
      <div><div className="help-eyebrow">If you feel unwell</div><h3>Getting help</h3></div></div>
    <a className="help-row urgent" href="tel:999"><b>Severe or sudden?</b><span>Call 999</span></a>
    <a className="help-row" href="tel:111"><b>Not urgent?</b><span>Call NHS 111 or your care team</span></a>
    {actions.length > 0 && <div className="help-letter"><small>Your letter says</small>
      <ul>{actions.map(a => <li key={a.action} className={a.urgency === 'emergency' ? 'emergency' : ''}>{a.action}</li>)}</ul></div>}
    <button type="button" className="help-dismiss" onClick={onDismiss}>I&apos;m feeling better</button>
  </section>;
}

export function TodayPanel(props: {
  items: PlanItem[]; justDone: PlanItem | null; reminderItemId: string | null; clock: string;
  dayAtHome: number | null; compact?: boolean; busy?: boolean; onDone?: (i: PlanItem) => void;
  empty?: boolean; onStart?: () => void;
  help?: HelpAction[] | null; onDismissHelp?: () => void;
}) {
  const { items, justDone } = props;
  const pending = items.filter(i => !i.done);
  const done = items.filter(i => i.done && i.id !== justDone?.id);
  const shown = pending.slice(0, justDone ? 1 : 2);
  const rest = pending.slice(shown.length);
  const slots = [...new Set(rest.map(i => i.slot))].sort((a, b) => slotOrder(a) - slotOrder(b));
  const doneCount = items.filter(i => i.done).length;
  return <div className={`panel grow${props.compact ? ' compact' : ''}`}>
    <div className="th">
      <div><div className="eyebrow">{props.dayAtHome ? `Day ${props.dayAtHome} at home` : 'At home'}</div><h2>Today</h2></div>
      <Ring done={doneCount} total={items.length} />
    </div>
    {/* Everything under the heading scrolls inside the panel instead of running off the screen */}
    <div className="tbody" tabIndex={0} role="region" aria-label="Today's plan">
    {props.help && <HelpCard actions={props.help} onDismiss={props.onDismissHelp || (() => {})} />}
    {/* What is already done comes first, then what is next and the rest of the day. */}
    {done.length > 0 && <div className="slotgrp donefirst">
      <div className="slot-h done">Done</div>
      <div className="items">{done.map(i => <Card key={i.id} item={i} due={null} />)}</div>
    </div>}
    <div className="lbl">{justDone ? 'Just done, then next up' : 'Next up'}</div>
    <div className="items">
      {justDone && <Card item={justDone} due={null} />}
      {shown.map(i => <Card key={i.id} item={i} due={i.id === props.reminderItemId ? dueText(i, props.clock) : null}
        onDone={props.onDone} busy={props.busy} />)}
    </div>
    {/* The rest of the day, as cards, by time of day. Every pending card has a "Mark as done" button;
        the report names the card's time of day, so a later card records its own occurrence. */}
    {rest.length > 0 && <div className="more">+ {rest.length} more today <span>&nbsp;by time of day</span></div>}
    {slots.map(s => <div key={s} className="slotgrp">
      <div className="slot-h">{s}</div>
      <div className="items">{rest.filter(i => i.slot === s).map(i => <Card key={i.id} item={i} due={null}
        onDone={props.onDone} busy={props.busy} />)}</div>
    </div>)}
    {props.empty && <>
      <p className="note">No plan for today yet. Upload a discharge letter first.</p>
      {props.onStart && <button type="button" className="back" onClick={props.onStart}>Back to start</button>}
    </>}
    </div>
  </div>;
}

// ---------- Letter panel (mock-ups 05 and 06) ----------

function Segments({ segments }: { segments: LetterBlock['segments'] }) {
  return <>{segments.map((s, i) => s.mark ? <mark key={i}>{s.text}</mark> : <span key={i}>{s.text}</span>)}</>;
}

// Paragraphs stay paragraphs; runs of numbered items or bullets become one list.
function LetterBody({ blocks, flag }: { blocks: LetterBlock[]; flag?: string | null }) {
  const out: ReactNode[] = [];
  // The flag ("Needs confirmation: ...") sits directly under the first marked line.
  const flagged = flag ? blocks.find(b => b.segments.some(s => s.mark)) : undefined;
  const flagFor = (b: LetterBlock) => b === flagged &&
    <span className="chip amber letterflag"><Icon name="alert" size={15} stroke={2} />{flag}</span>;
  for (let i = 0; i < blocks.length;) {
    const kind = blocks[i].kind;
    if (kind === 'para') {
      out.push(<p key={i} className="txt"><Segments segments={blocks[i].segments} />{flagFor(blocks[i])}</p>);
      i += 1;
      continue;
    }
    let j = i;
    while (j < blocks.length && blocks[j].kind === kind) j += 1;
    const run = blocks.slice(i, j);
    out.push(kind === 'item'
      ? <ol key={i} className="letterlist2" start={Number(run[0].number) || 1}>
          {run.map((b, k) => <li key={k} className="txt"><Segments segments={b.segments} />{flagFor(b)}</li>)}</ol>
      : <ul key={i} className="letterlist2">
          {run.map((b, k) => <li key={k} className="txt"><Segments segments={b.segments} />{flagFor(b)}</li>)}</ul>);
    i = j;
  }
  return <>{out}</>;
}

export function LetterPanel({ source, onBack }: { source: NonNullable<Source>; onBack: () => void }) {
  const blocks = letterBlocks(source);
  // A list of several rows (the medicines) is set smaller, so every row and the marked one fit without scrolling.
  const list = blocks.length >= 3;
  return <section className="panel grow letter-panel" aria-label="Passage from your discharge letter">
    <header className="letter-heading">
      <div className="letter-heading-icon"><Icon name="doc" size={25} /></div>
      <div className="letter-heading-copy">
        <div className="eyebrow rose">From your discharge letter</div>
        <h2>{source.section || 'Your letter, in its own words'}</h2>
      </div>
      {source.page && <span className="letter-page">Page {source.page}</span>}
    </header>
    <p className="letter-intro">The passage behind AfterWard’s answer.</p>
    <div className={`paper letter-excerpt${list ? ' is-list' : ''}`}>
      <div className="letter-paper-top">
        <span>Letter excerpt</span>
        {source.highlight && <span className="letter-key"><i />Relevant wording</span>}
      </div>
      <div className="letter-scroll" tabIndex={0} role="region" aria-label="Original letter passage">
        <div className="in letterbody">
          {/* One card for what the letter says, and one for each appointment it points at. */}
          <div className="quotecard">
            <div className="quotehead"><span>Your letter says</span>{source.page && <b>Page {source.page}</b>}</div>
            <LetterBody blocks={blocks} flag={source.note?.flag} />
          </div>
          {(source.related || []).map((r, i) => <div key={i} className="quotecard linked">
            <div className="quotehead"><span>Linked appointment</span>{r.page && <b>Page {r.page}</b>}</div>
            <p className="txt">{r.text}</p>
          </div>)}
        </div>
      </div>
      <div className="letter-paper-bottom"><Icon name="doc" size={15} />Original wording · Synthetic demo document</div>
    </div>
    {source.note?.text && <p className="letter-note">{source.note.text}</p>}
    <footer className="letter-actions">
      <button type="button" className="letter-back" onClick={onBack}>
        <span className="letter-back-arrow"><Icon name="arrow" size={19} /></span>Back to today
      </button>
      <span>Your plan is still here.</span>
    </footer>
  </section>;
}

// ---------- Voice panel (the dark panel on the right) ----------

export type Turn = { who: 'you' | 'aw'; text: string; reminder?: boolean };

const WAVE = [10, 22, 32, 18, 28, 12, 20];
const RINGS = <div className="ringbox"><svg className="rings" width="520" height="520" viewBox="0 0 520 520" fill="none" stroke="currentColor">
  {[[62, .45], [104, .24], [156, .12]].map(([r, o]) => <circle key={r} cx="260" cy="260" r={r} strokeOpacity={o} strokeWidth="1.5" />)}</svg></div>;

export function VoicePanel(props: {
  head: string; turns: Turn[]; chips: { kind: string; icon: string; text: string }[];
  speaking: boolean; listening: boolean; busy: boolean; canListen: boolean; typing: boolean;
  onMic: () => void; onSend: (text: string) => void; onToggleTyping: () => void;
}) {
  // Show her last question and the answer. Keep the reminder on screen for the first reply to it.
  const n = props.turns.length;
  const shown = props.turns.slice(n >= 3 && props.turns[n - 3].reminder ? -3 : -2);
  const lastAw = shown.map(t => t.who).lastIndexOf('aw');
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const input = e.currentTarget.elements.namedItem('msg') as HTMLInputElement;
    if (input.value.trim()) { props.onSend(input.value.trim()); input.value = ''; }
  };
  const state = props.busy ? ['Thinking', 'AfterWard is checking her plan.']
    : props.listening ? ['Listening', 'Speak now.']
    : props.speaking ? ['Speaking', 'The same words are on screen.']
    : ['Listening', props.canListen ? 'Tap the microphone, tap Mark as done, or type.' : 'Type below. This browser cannot listen.'];
  return <div className={`panel voice${props.speaking ? ' speaking' : ''}`} aria-live="polite">
    {RINGS}
    <div className="vhead"><Logo size={26} /><span>{props.head}</span></div>
    <div className="turns">
      {shown.map((t, i) => t.who === 'you'
        ? <div key={i} className="turn you"><small>You said</small><p>&ldquo;{t.text}&rdquo;</p></div>
        : <div key={i} className={`turn aw${i === lastAw ? '' : ' past'}${t.text.length > 150 ? ' long' : ''}`}><small>AfterWard</small><p>{t.text}</p></div>)}
      {props.chips.length > 0 && <div className="proof">{props.chips.map(c =>
        <span key={c.text} className={`pchip ${c.kind}`}><Icon name={c.icon} size={16} stroke={2.3} />{c.text}</span>)}</div>}
    </div>
    <div className="grow" />
    {(props.typing || !props.canListen) && <form className="typebox" onSubmit={submit}>
      <input name="msg" placeholder="Type to AfterWard…" aria-label="Type a message" disabled={props.busy} autoComplete="off" />
      <button type="submit" disabled={props.busy}>Send</button></form>}
    <div className="listen">
      <button type="button" className="micbtn" onClick={props.onMic} disabled={props.busy || !props.canListen}
        aria-label={props.listening ? 'Listening' : 'Talk to AfterWard'}><Icon name="mic" size={26} stroke={2} /></button>
      <div className="h"><b>{state[0]}</b>{state[1]}</div>
      {props.speaking && !props.busy ? <span className="wave">{WAVE.map((h, i) => <i key={i} style={{ height: h }} />)}</span>
        : props.canListen && <button type="button" className="typelink" onClick={props.onToggleTyping}>{props.typing ? 'Hide' : 'Type'}</button>}
    </div>
  </div>;
}

// ---------- Developer view (mock-up 09) ----------

// Keeps a scrolling list on its newest entry: when `count` grows, the list scrolls to the end.
// Everything earlier stays in the list, a scroll away.
function useFollowNewest(count: number) {
  const list = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (list.current) list.current.scrollTop = list.current.scrollHeight;
  }, [count]);
  return list;
}

export function ConversationLog({ turns }: { turns: Turn[] }) {
  const list = useFollowNewest(turns.length);
  return <div className="panel" style={{ width: 384, flex: 'none', padding: '20px 20px' }}>
    <div className="eyebrow" style={{ marginBottom: 12 }}>Conversation</div>
    <div className="legend">Margaret on the right, AfterWard on the left</div>
    <div className="msgs" ref={list} tabIndex={0} role="log" aria-label="The whole conversation">{turns.map((t, i) =>
      <div key={i} className={`msg ${t.who === 'you' ? 'me' : 'aw'}`}>{t.text}</div>)}</div>
  </div>;
}

export function ToolPanel({ calls, requestId }: { calls: ToolCall[]; requestId: string | null }) {
  // Every call of the session, oldest first, so an earlier write (a walk recorded
  // three turns ago) can still be scrolled back to.
  const list = useFollowNewest(calls.length);
  return <div className="panel tools" style={{ width: 376, flex: 'none', padding: '20px 22px' }}>
    <div className="vhead" style={{ marginBottom: 8 }}><Icon name="code" size={17} stroke={2} />MCP tool calls · spec 2025-11-25</div>
    <div className="calls" ref={list} tabIndex={0} role="log" aria-label="Every tool call this session">
      {calls.length === 0 && <p className="call"><span className="arg">No tool calls yet. Ask AfterWard something.</span></p>}
      {calls.map((c, i) => <div key={i} className="call">
        <b>{c.name}<i className={c.kind}>{c.kind}</i></b>
        <span className="arg">{c.args}</span><br /><span className="res">{c.result}</span>
      </div>)}
    </div>
    {/* The last chat turn's ID: search the logs for it to see the bridge, agent and tool lines. */}
    {requestId && <div className="reqid" title="Search the server logs for this ID">request_id <span>{requestId}</span></div>}
  </div>;
}

export { prettyTime };
