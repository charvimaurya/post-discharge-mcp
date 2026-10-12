// Turns the bridge's /today and /chat replies into the simple shapes the screen needs.
// All field-name guessing lives here. If a field in your bridge has a different name,
// this is the only file to change.

export type PlanItem = {
  id: string;
  kind: 'task' | 'medicine';
  name: string;              // "Short walk with your walking frame" or "Paracetamol"
  title: string;             // name plus dose: "Paracetamol, 2 tablets"
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
export type Today = { clockLabel: string; items: PlanItem[]; pendingCheckin: Checkin | null };
export type ToolCall = { name: string; kind: 'read' | 'write'; args: string; result: string };
export type Source = { text: string; page: number | null } | null;
export type ChatReply = { text: string; tools: ToolCall[]; source: Source; completed: boolean };

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

function toItem(o: Obj, kind: PlanItem['kind']): PlanItem {
  const source = isObj(o.source) ? o.source : {};
  const name = str(pick(o, 'name', 'title', 'description', 'what', 'text')) || 'Untitled item';
  const dose = kind === 'medicine' ? str(pick(o, 'dose', 'amount')) : '';
  const clockTime = str(pick(o, 'clock_time', 'time')) || null;
  const slot = cap(str(pick(o, 'time_of_day_label', 'time_of_day', 'slot'))) || 'Any time';
  const extra = str(pick(o, 'details', 'instructions'));
  const status = str(pick(o, 'status')).toLowerCase();
  return {
    id: str(pick(o, 'occurrence_id', 'id', 'task_id', 'medication_id')) || name,
    kind,
    name,
    title: dose ? `${name}, ${dose}` : name,
    detail: [clockTime ? prettyTime(clockTime) : slot, extra].filter(Boolean).join(', '),
    slot,
    clockTime,
    done: ['completed', 'done', 'taken'].includes(status) || o.completed === true,
    doneAt: str(pick(o, 'completed_at', 'done_at', 'taken_at')) || null,
    needsConfirmation: o.needs_confirmation === true,
    confirmationText: str(pick(o, 'confirmation_reason', 'unclear_reason')) || null,
    quote: str(pick(source, 'snippet', 'text')) || null,
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
  const tasks = listFrom(o.tasks, 'tasks').map(t => toItem(t, 'task'));
  const meds = listFrom(o.medications, 'medications')
    .filter(m => m.as_needed !== true)          // "only if needed" medicines are not part of the day's list
    .map(m => toItem(m, 'medicine'));
  const items = sortItems([...tasks, ...meds]);
  addRepeats(items);
  const p = isObj(o.pending_checkin) ? o.pending_checkin : null;
  return {
    clockLabel: str(o.clock_label),
    items,
    pendingCheckin: p
      ? {
          id: str(pick(p, 'checkin_id', 'id', 'checkin_key', 'occurrence_id')) || str(pick(p, 'text', 'message')),
          text: str(pick(p, 'text', 'message', 'prompt', 'reminder_text')),
          itemId: str(pick(p, 'occurrence_id', 'item_id')) || null,
        }
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

export function readChat(json: unknown): ChatReply {
  const o = isObj(json) ? json : {};
  const tools = (Array.isArray(o.tool_trace) ? o.tool_trace : []).filter(isObj).map(t => {
    const name = str(pick(t, 'name', 'tool', 'tool_name'));
    return {
      name,
      kind: name.startsWith('report_') ? 'write' as const : 'read' as const,
      args: short(pick(t, 'arguments', 'args', 'input')) || 'no arguments',
      result: short(pick(t, 'summary', 'result', 'output', 'content')),
    };
  });
  const s = isObj(o.source) ? o.source : null;
  const text = s ? str(pick(s, 'snippet', 'text', 'passage')) : '';
  return {
    text: str(pick(o, 'response', 'reply', 'message')),
    tools,
    source: text ? { text, page: Number(pick(s as Obj, 'page')) || null } : null,
    completed: o.completed !== false,
  };
}

// ---------- The whole plan, for the screen shown right after upload ----------

export type PlanRow = { section: 'Medicines' | 'Each day' | 'Appointments'; text: string; when: string; flag: string | null };
export type PlanSummary = { rows: PlanRow[]; quotes: { text: string; flagged: boolean }[]; mustNot: number; warnings: number };

export function readPlan(state: Obj): PlanSummary {
  const list = (k: string) => (Array.isArray(state[k]) ? (state[k] as unknown[]).filter(isObj) : []);
  const rows: PlanRow[] = [];
  const quotes: PlanSummary['quotes'] = [];
  for (const m of list('medications')) {
    const name = str(pick(m, 'name')) || 'Medicine';
    const dose = str(pick(m, 'dose'));
    const times = Number(pick(m, 'times_per_day')) || 0;
    const when = m.as_needed === true ? 'only if needed' : times === 1 ? 'once a day' : times === 2 ? 'twice a day' : times ? `${times} times a day` : str(pick(m, 'time_of_day'));
    rows.push({ section: 'Medicines', text: dose ? `${name}, ${dose}` : name, when, flag: m.needs_confirmation === true ? 'Needs confirmation' : null });
    const snippet = isObj(m.source) ? str(m.source.snippet) : '';
    if (snippet) quotes.push({ text: snippet, flagged: m.needs_confirmation === true });
  }
  for (const t of list('tasks')) {
    const name = str(pick(t, 'name', 'title', 'description')) || 'Task';
    const clock = Array.isArray(t.clock_times) ? (t.clock_times as unknown[]).map(c => prettyTime(str(c))).join(' and ') : '';
    const times = Number(pick(t, 'times_per_day')) || 0;
    rows.push({ section: 'Each day', text: name, when: clock || (times ? `${times} times a day` : str(pick(t, 'time_of_day'))), flag: t.needs_confirmation === true ? 'Needs confirmation' : null });
  }
  for (const a of list('appointments')) {
    const name = str(pick(a, 'title', 'name', 'description', 'what')) || 'Appointment';
    const when = [str(pick(a, 'date')), prettyTime(str(pick(a, 'time')) || null)].filter(Boolean).join(', ');
    rows.push({ section: 'Appointments', text: name, when, flag: a.needs_confirmation === true ? 'Needs confirmation' : null });
  }
  return { rows, quotes, mustNot: list('restrictions').length, warnings: list('warning_signs').length };
}
