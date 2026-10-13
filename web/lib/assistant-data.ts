// Turns the bridge's /today and /chat replies into the simple shapes the screen needs.
// All field-name guessing lives here. If a field in your bridge has a different name,
// this is the only file to change.

export type PlanItem = {
  id: string;
  kind: 'task' | 'medicine';
  name: string;              // "Short walk with your walking frame" or "Paracetamol"
  title: string;             // medicines: name plus dose, "Paracetamol, 2 tablets"; tasks: short label, "Walk"
  detail: string;            // "7:30 am, with your walking frame" or "Morning"
  slot: string;              // "Morning", "Midday", "Afternoon", "Evening", "Bedtime" or "Any time"
  clockTime: string | null;  // "07:30" (tasks only)
  done: boolean;
  doneAt: string | null;     // ISO time it was completed
  needsConfirmation: boolean;
  confirmationText: string | null;
  quote: string | null;      // the sentence from the letter
  page: number | null;
  repeat: { index: number; total: number; doneInGroup: number } | null; // walk 1 of 2
};

export type Checkin = { id: string; text: string; itemId: string | null };
export type Today = {
  clockLabel: string;
  openingGreeting: string;
  date: string | null;           // "2026-10-23", the server's "today"
  dischargeDate: string | null;  // "2026-10-16"
  items: PlanItem[];
  pendingCheckin: Checkin | null;
};
export type ToolCall = { name: string; kind: 'read' | 'write'; args: string; result: string; ok: boolean };
// text: the letter passage; highlight: the one line the reply relied on.
// text: the clean excerpt (or, from an older bridge, the raw passage); highlight: the sentence that answers;
// section: the letter heading above it, e.g. "Medicines".
// related: the letter's own line for an appointment the passage refers to ("Consultant review: ...").
export type RelatedLine = { text: string; page: number | null };
// note: shown under the marked line when the letter leaves something open ("no end date").
export type SourceNote = { flag: string; text: string };
export type Source = { text: string; highlight: string | null; page: number | null; section: string | null; related?: RelatedLine[]; note?: SourceNote | null } | null;
// saved: a report_* tool ran and succeeded, so something really was written to the plan.
// requestId: the ID this turn has in every server log line (shown small in Developer view).
// "Get help" card: who to call, in the letter's own words. Only set on a symptom reply.
export type HelpAction = { urgency: string; action: string };
export type ChatReply = { text: string; tools: ToolCall[]; source: Source; completed: boolean; saved: boolean; requestId: string | null; help: HelpAction[] | null };

type Obj = Record<string, unknown>;
export const isObj = (v: unknown): v is Obj => !!v && typeof v === 'object' && !Array.isArray(v);
export const str = (v: unknown): string => (typeof v === 'string' ? v : typeof v === 'number' ? String(v) : '');
const pick = (o: Obj, ...keys: string[]): unknown => {
  for (const k of keys) if (o[k] !== undefined && o[k] !== null && o[k] !== '') return o[k];
  return undefined;
};

// An MCP tool result can arrive as a plain list, as { tasks: [...] }, or wrapped in structuredContent.
export function listFrom(value: unknown, ...keys: string[]): Obj[] {
  if (Array.isArray(value)) return value.filter(isObj);
  if (!isObj(value)) return [];
  for (const k of [...keys, 'items', 'occurrences', 'data', 'result']) {
    if (Array.isArray(value[k])) return (value[k] as unknown[]).filter(isObj);
  }
  if (value.structuredContent !== undefined) return listFrom(value.structuredContent, ...keys);
  return [];
}

const SLOTS = ['Morning', 'Midday', 'Afternoon', 'Evening', 'Bedtime'];
export const slotOrder = (slot: string) => {
  const i = SLOTS.indexOf(slot);
  return i === -1 ? SLOTS.length : i;
};
const cap = (s: string) => (s ? s[0].toUpperCase() + s.slice(1).toLowerCase() : s);

// "07:30" -> "Morning", "15:00" -> "Afternoon". Same boundaries as app/reminders/text.py.
export function slotForClock(hhmm: string | null): string | null {
  const m = /^(\d{1,2}):\d{2}/.exec(hhmm || '');
  if (!m) return null;
  const h = Number(m[1]);
  return h < 12 ? 'Morning' : h < 14 ? 'Midday' : h < 17 ? 'Afternoon' : h < 21 ? 'Evening' : 'Bedtime';
}

// "07:30" -> "7:30 am"
export function prettyTime(hhmm: string | null): string {
  if (!hhmm) return '';
  const m = /(\d{1,2}):(\d{2})/.exec(hhmm);
  if (!m) return hhmm;
  const h = Number(m[1]);
  return `${h % 12 || 12}:${m[2]} ${h < 12 ? 'am' : 'pm'}`;
}

// An ISO time such as 2026-10-23T06:50:00+00:00 -> "7:50 am" in the patient's time zone.
export function localTime(iso: string | null, timeZone = 'Europe/London'): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return prettyTime(iso);
  return d.toLocaleTimeString('en-GB', { hour: 'numeric', minute: '2-digit', hour12: true, timeZone })
    .replace(/\s/g, ' ').toLowerCase();
}

// "Friday 23 October, 07:00" -> { day: "Friday 23 October", time: "7:00 am" }
export function splitClock(label: string): { day: string; time: string } {
  const m = /^(.*?),?\s+(\d{1,2}:\d{2})/.exec(label);
  return m ? { day: m[1], time: prettyTime(m[2]) } : { day: label, time: '' };
}

// Whole days between discharge and today, from two "YYYY-MM-DD" dates. Null if either is missing.
export function daysAtHome(date: string | null, dischargeDate: string | null): number | null {
  const day = (s: string | null) => (s && /^\d{4}-\d{2}-\d{2}/.test(s) ? Date.parse(`${s.slice(0, 10)}T00:00:00Z`) : NaN);
  const days = Math.round((day(date) - day(dischargeDate)) / 86_400_000);
  return Number.isFinite(days) && days > 0 ? days : null;
}

// A short on-screen name for a task, from the letter's own words (same rule as
// short_task_name in app/reminders/text.py): "Walking: one short walk ..." -> "Walk",
// "Knee exercises from your physiotherapy sheet: ..." -> "Knee exercises".
// The full sentence is still shown as the quote from the letter.
export function shortTaskLabel(description: string): string {
  if (/walk/i.test(description)) return 'Walk';
  const first = description.trim().split(/(?<=[.!?])\s/)[0];
  const head = first.split(/:|,| from | for /)[0].trim().replace(/\.$/, '');
  return head ? head[0].toUpperCase() + head.slice(1) : description;
}

// Medicines carry "name"; tasks carry "description".
function toItem(o: Obj, kind: PlanItem['kind']): PlanItem {
  const source = isObj(o.source) ? o.source : {};
  const name = str(pick(o, 'name', 'description', 'title')) || 'Untitled item';
  const dose = kind === 'medicine' ? str(pick(o, 'dose', 'amount')) : '';
  const clockTime = str(o.clock_time) || null;                // tasks only
  // A walk may have a clock time from the letter but no time-of-day word, so group it by its time.
  const slot = cap(str(o.time_of_day_label)) || slotForClock(clockTime) || 'Any time';
  const extra = str(pick(o, 'details', 'instructions'));
  const status = str(o.status).toLowerCase();               // "pending" or "completed"
  return {
    id: str(pick(o, 'occurrence_id', 'id')) || name,
    kind,
    name,
    title: kind === 'task' ? shortTaskLabel(name) : dose ? `${name}, ${dose}` : name,
    detail: [clockTime ? prettyTime(clockTime) : slot, extra].filter(Boolean).join(', '),
    slot,
    clockTime,
    done: status === 'completed',
    doneAt: str(o.completed_at) || null,
    needsConfirmation: o.needs_confirmation === true,
    // The plan has no reason text yet, so the screen shows "Needs confirmation".
    confirmationText: str(o.confirmation_reason) || null,
    quote: str(source.snippet) || null,
    page: Number(pick(source, 'page')) || null,
    repeat: null,
  };
}

// Number repeated items, so the walk shows "1 of 2". Occurrence IDs look like task_abc#2026-10-23#1.
function addRepeats(items: PlanItem[]) {
  const groups = new Map<string, PlanItem[]>();
  for (const it of items) {
    const key = it.id.split('#')[0];
    groups.set(key, [...(groups.get(key) || []), it]);
  }
  for (const group of groups.values()) {
    if (group.length < 2) continue;
    const doneInGroup = group.filter(i => i.done).length;
    group.forEach((it, i) => (it.repeat = { index: i + 1, total: group.length, doneInGroup }));
  }
}

export function sortItems(items: PlanItem[]): PlanItem[] {
  return [...items].sort((a, b) =>
    slotOrder(a.slot) - slotOrder(b.slot)
    || (a.clockTime || '99').localeCompare(b.clockTime || '99')
    || (a.kind === b.kind ? 0 : a.kind === 'task' ? -1 : 1));
}

export function readToday(json: unknown): Today {
  const o = isObj(json) ? json : {};
  // /today sends plain lists: tasks from get_today_tasks, medications from get_medications.
  const tasks = listFrom(o.tasks, 'tasks').map(t => toItem(t, 'task'));
  const meds = listFrom(o.medications, 'medications')
    .filter(m => m.as_needed !== true)          // "only if needed" medicines are not part of the day's list
    .map(m => toItem(m, 'medicine'));
  const items = sortItems([...tasks, ...meds]);
  addRepeats(items);
  // Written by lambdas/reminder_checker/handler.py: checkin_id, occurrence_id, text, ...
  const p = isObj(o.pending_checkin) ? o.pending_checkin : null;
  return {
    clockLabel: str(o.clock_label),
    openingGreeting: str(o.opening_greeting),
    date: str(o.date) || null,
    dischargeDate: str(o.discharge_date) || null,
    items,
    pendingCheckin: p && str(p.checkin_id) && str(p.text)
      ? { id: str(p.checkin_id), text: str(p.text), itemId: str(p.occurrence_id) || null }
      : null,
  };
}

function short(v: unknown, max = 110): string {
  if (v === undefined || v === null) return '';
  let s = typeof v === 'string' ? v : JSON.stringify(v);
  if (isObj(v) && typeof v.summary === 'string') s = v.summary;
  if (s === '{}') return '';
  return s.length > max ? `${s.slice(0, max - 1)}…` : s;
}

// The bridge's /chat reply: { response, tool_trace: [{ tool, arguments, ok }], source, session_id }.
// source comes from app/agent/evidence.py: { document_id, page, chunk_id, passage, highlighted_line }.
export function readChat(json: unknown): ChatReply {
  const o = isObj(json) ? json : {};
  const tools = (Array.isArray(o.tool_trace) ? o.tool_trace : []).filter(isObj).map(t => {
    const name = str(t.tool);
    const ok = t.ok === true;
    // blocked: a write AfterWard held back because she said she had not done it. Nothing was saved.
    return {
      name,
      kind: name.startsWith('report_') || name === 'schedule_checkin' || name === 'undo_report' ? 'write' as const : 'read' as const,
      args: short(t.arguments) || 'no arguments',
      result: t.blocked === true ? 'not recorded' : ok ? 'ok' : 'failed',
      ok,
    };
  });
  // source from app/agent/evidence.py: { page, section, text, highlight } plus the older
  // { passage, highlighted_line }, which are used only when the newer fields are missing.
  const s = isObj(o.source) ? o.source : null;
  const text = s ? str(s.text) || str(s.passage) : '';
  const highlight = s ? str(s.highlight) || str(s.highlighted_line) : '';
  const related: RelatedLine[] = (s && Array.isArray(s.related) ? s.related : []).filter(isObj)
    .map(r => ({ text: str(r.text), page: Number(r.page) || null })).filter(r => r.text);
  const note: SourceNote | null = s && isObj(s.note) && str(s.note.flag) ? { flag: str(s.note.flag), text: str(s.note.text) } : null;
  return {
    text: str(o.response),
    tools,
    source: text || highlight
      ? { text: text || highlight, highlight: highlight || null, page: Number(s?.page) || null, section: s ? str(s.section) || null : null, related, note }
      : null,
    completed: o.completed !== false,
    saved: tools.some(t => t.kind === 'write' && t.ok),
    requestId: str(o.request_id) || null,
    help: isObj(o.help) && Array.isArray(o.help.actions)
      ? o.help.actions.filter(isObj).map(a => ({ urgency: str(a.urgency), action: str(a.action) })).filter(a => a.action)
      : null,
  };
}

// The letter excerpt as short paragraphs and list items, with the answering sentence marked.
export type LetterSegment = { text: string; mark: boolean };
export type LetterBlock = { kind: 'para' | 'item' | 'bullet'; number: string | null; segments: LetterSegment[] };

const words = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();

// ---------- Which plan items an answer is about ----------
// Same everyday name AfterWard says aloud (app/agent/occurrence_resolver.py: _EVERYDAY_NAMES).
const BLOOD_THINNERS = ['apixaban', 'rivaroxaban', 'edoxaban', 'dabigatran', 'warfarin', 'enoxaparin', 'dalteparin', 'heparin'];
const SLOT_WORDS: Record<string, string[]> = {
  morning: ['morning', 'breakfast'], midday: ['midday', 'lunch'], afternoon: ['afternoon'],
  evening: ['evening', 'dinner', 'supper'], bedtime: ['bedtime', 'bed time', 'night'],
};

// The words AfterWard could use for this item: "paracetamol", "blood thinner", "walk", "knee exercises".
function spokenNames(item: PlanItem): string[] {
  const name = words(item.name);
  if (item.kind === 'medicine') {
    const out = [name.split(' ')[0]];
    if (BLOOD_THINNERS.some(b => name.includes(b))) out.push('blood thinner');
    return out.filter(Boolean);
  }
  if (name.includes('walk')) return ['walk'];
  if (name.includes('exercise')) return ['exercise'];
  return [words(item.title).split(' ')[0]].filter(Boolean);
}

/**
 * The ids of the plan items an answer names, so the Today screen can point at them.
 * Nothing is guessed: an item is picked only when its name is in the reply. For each
 * name, the next item not yet done is chosen, in the part of the day the reply names
 * ("after breakfast" is morning) when it names one.
 */
export function itemsMentioned(reply: string, items: PlanItem[]): string[] {
  const said = ` ${words(reply)} `;
  const slots = Object.entries(SLOT_WORDS).filter(([, ws]) => ws.some(w => said.includes(` ${w}`))).map(([s]) => s);
  const byName = new Map<string, PlanItem[]>();
  for (const item of items) {
    for (const n of spokenNames(item)) {
      if (!said.includes(` ${n}`)) continue;
      byName.set(n, [...(byName.get(n) || []), item]);
      break;
    }
  }
  const ids: string[] = [];
  for (const group of byName.values()) {
    // The named part of the day first ("your morning walk done" is the morning one, even
    // though it is done), then the next one not yet done, then any.
    const inSlot = group.filter(i => slots.includes(i.slot.toLowerCase()));
    const pending = (list: PlanItem[]) => list.filter(i => !i.done);
    const pick = [pending(inSlot), inSlot, pending(group), group].find(l => l.length)?.[0];
    if (pick && !ids.includes(pick.id)) ids.push(pick.id);
  }
  return ids;
}

function markHighlight(text: string, highlight: string | null): LetterSegment[] {
  if (!highlight) return [{ text, mark: false }];
  const at = text.indexOf(highlight);
  if (at >= 0) {
    return [
      { text: text.slice(0, at), mark: false },
      { text: highlight, mark: true },
      { text: text.slice(at + highlight.length), mark: false },
    ].filter(s => s.text);
  }
  // Older replies: the highlight is a whole letter item, matched by its words.
  const w = words(text), h = words(highlight);
  return [{ text, mark: !!w && !!h && (w.includes(h) || h.includes(w)) }];
}

export function letterBlocks(source: NonNullable<Source>): LetterBlock[] {
  const lines = source.text.split(/\n+/).map(l => l.trim()).filter(Boolean);
  const blocks = lines.map(line => {
    const numbered = /^(\d+)\.\s+(.*)$/.exec(line);
    if (numbered) return { kind: 'item' as const, number: numbered[1], segments: markHighlight(numbered[2], source.highlight) };
    if (line.startsWith('- ')) return { kind: 'bullet' as const, number: null, segments: markHighlight(line.slice(2), source.highlight) };
    return { kind: 'para' as const, number: null, segments: markHighlight(line, source.highlight) };
  });
  // If the answering sentence is not in the text at all, still show it, marked, first.
  if (source.highlight && !blocks.some(b => b.segments.some(s => s.mark))) {
    blocks.unshift({ kind: 'para', number: null, segments: [{ text: source.highlight, mark: true }] });
  }
  return blocks;
}

// ---------- The whole plan, for the screen shown right after upload ----------

export type PlanRow = { section: 'Medicines' | 'Each day' | 'Appointments'; text: string; when: string; flag: string | null };
export type PlanSummary = {
  rows: PlanRow[]; quotes: { text: string; flagged: boolean }[]; taskQuotes: string[];
  mustNot: number; warnings: number; careNotes: number;
};

// "2026-10-22" -> "Thu 22 Oct". Anything else is shown as written.
function shortDate(date: string): string {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return date;
  return new Date(`${date}T00:00:00Z`).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', timeZone: 'UTC' });
}

export function readPlan(state: Obj): PlanSummary {
  const list = (k: string) => (Array.isArray(state[k]) ? (state[k] as unknown[]).filter(isObj) : []);
  const rows: PlanRow[] = [];
  const quotes: PlanSummary['quotes'] = [];
  const taskQuotes: string[] = [];
  for (const m of list('medications')) {
    const name = str(pick(m, 'name')) || 'Medicine';
    const dose = str(pick(m, 'dose'));
    const times = Number(pick(m, 'times_per_day')) || 0;
    const when = m.as_needed === true ? 'only if needed' : times === 1 ? 'once a day' : times === 2 ? 'twice a day' : times ? `${times} times a day` : str(pick(m, 'time_of_day'));
    // "Paracetamol 500 mg tablets" -> "Paracetamol" in the plan; the letter side keeps the full name.
    const shortName = name.replace(/\s+\d.*$/, '') || name;
    rows.push({ section: 'Medicines', text: dose ? `${shortName}, ${dose}` : shortName, when, flag: m.needs_confirmation === true ? 'Needs confirmation' : null });
    const snippet = isObj(m.source) ? str(m.source.snippet) : '';
    if (snippet) quotes.push({ text: snippet.toLowerCase().startsWith(name.toLowerCase()) ? snippet : `${name}. ${snippet}`, flagged: m.needs_confirmation === true });
  }
  for (const t of list('tasks')) {
    const name = str(pick(t, 'name', 'title', 'description')) || 'Task';
    const clock = Array.isArray(t.clock_times) ? (t.clock_times as unknown[]).map(c => prettyTime(str(c))).join(' and ') : '';
    const times = Number(pick(t, 'times_per_day')) || 0;
    const taskSnippet = isObj(t.source) ? str(t.source.snippet) : '';
    if (taskSnippet) taskQuotes.push(taskSnippet);
    rows.push({ section: 'Each day', text: shortTaskLabel(name), when: clock || (times ? `${times} times a day` : str(pick(t, 'time_of_day'))), flag: t.needs_confirmation === true ? 'Needs confirmation' : null });
  }
  for (const a of list('appointments')) {
    const name = str(pick(a, 'title', 'name', 'description', 'what')) || 'Appointment';
    const when = [shortDate(str(pick(a, 'date'))), prettyTime(str(pick(a, 'time')) || null)].filter(Boolean).join(', ');
    rows.push({ section: 'Appointments', text: name, when, flag: a.needs_confirmation === true ? 'Needs confirmation' : null });
  }
  return {
    rows, quotes, taskQuotes, mustNot: list('restrictions').length, warnings: list('warning_signs').length,
    careNotes: list('diet_advice').length + list('monitoring').length,
  };
}
