import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { loadBindings, transform } from 'next/dist/build/swc/index.js';
import { calendarDays, dayProgress, fetchRecoverySnapshot, readRecoveryDay, recordedTime } from '../lib/recovery-dashboard.ts';
import { readWeekSummary } from '../lib/week-summary.ts';

function day(date = '2026-10-23') {
  return { kind: 'recovery_day_details', schema_version: 1, date, timezone: 'Europe/London',
    scope: 'all_scheduled', schedule_evidence: 'snapshot', synthetic_demo_history: true,
    medications: [{ occurrence_id: `a#${date}#1`, name: '<script>unsafe</script>', dose: '1 demo tablet',
      period: 'morning', due_at: `${date}T06:30:00+01:00`, status: 'taken', recorded_at: `${date}T06:45:00+01:00` }],
    tasks: [{ occurrence_id: `walk#${date}#1`, name: 'Synthetic walk', status: 'completed', recorded_at: `${date}T06:50:00+01:00` }] };
}
const weekPayload = () => ({ week: { discharge_date: '2026-10-20', days: Array.from({ length: 7 }, (_, i) => ({ date: `2026-10-${17 + i}`,
  is_today: i === 6, status: i === 6 ? 'completed' : 'unknown' })),
  activity: Array.from({ length: 7 }, (_, i) => ({ date: `2026-10-${17 + i}`, completed_tasks: i === 6 ? 1 : 0 })) } });

test('daily parser refuses wrong dates, duplicate doses, missing timestamps and unsupported statuses', () => {
  assert.ok(readRecoveryDay(day(), '2026-10-23'));
  assert.equal(readRecoveryDay(day(), '2026-10-22'), null);
  for (const mutate of [
    (p: ReturnType<typeof day>) => { p.medications[0].recorded_at = ''; },
    (p: ReturnType<typeof day>) => { p.medications.push(p.medications[0]); },
    (p: ReturnType<typeof day>) => { p.medications[0].status = 'completed'; },
    (p: ReturnType<typeof day>) => { p.timezone = 'bad/zone'; },
    (p: ReturnType<typeof day>) => { p.tasks[0].status = 'taken'; },
  ]) { const p = day(); mutate(p); assert.equal(readRecoveryDay(p, '2026-10-23'), null); }
  assert.match(recordedTime('2026-10-23T06:45:00+01:00', 'Europe/London'), /06:45/);
});

test('refresh reads every calendar day and sees updated persisted results without patient selectors', async () => {
  let count = 0;
  const urls: string[] = [];
  const fetcher = async (url: any, init?: RequestInit) => {
    urls.push(String(url)); assert.equal(init?.cache, 'no-store');
    if (String(url).includes('week-summary')) return Response.json(weekPayload());
    const date = String(url).split('date=')[1];
    const p = day(date);
    if (date === '2026-10-22') {
      p.medications[0].status = count++ ? 'taken' : 'unknown';
      if (count === 1) p.medications[0].recorded_at = null as any;
    }
    return Response.json(p);
  };
  const signal = new AbortController().signal;
  const first = await fetchRecoverySnapshot('2026-10-22', signal, fetcher);
  assert.equal(first.day.medications[0].status, 'unknown');
  assert.deepEqual(Object.keys(first.days), ['2026-10-21', '2026-10-22', '2026-10-23']);
  assert.equal((await fetchRecoverySnapshot('2026-10-22', signal, fetcher)).day.medications[0].status, 'taken');
  const days = ['/api/recovery-day?date=2026-10-21', '/api/recovery-day?date=2026-10-22', '/api/recovery-day?date=2026-10-23'];
  assert.deepEqual(urls, ['/api/week-summary', ...days, '/api/week-summary', ...days]);
  await assert.rejects(fetchRecoverySnapshot('', signal, async () => Response.json({}, { status: 502 })));
});

test('date selection outside the calendar falls back to today', async () => {
  for (const selected of ['1900-01-01', '2026-10-20']) {
    const result = await fetchRecoverySnapshot(selected, new AbortController().signal,
      async (url: any) => Response.json(String(url).includes('week-summary') ? weekPayload() : day(String(url).split('date=')[1])));
    assert.equal(result.date, '2026-10-23');
  }
});

test('a day is done only when every task and dose is recorded', () => {
  const p = readRecoveryDay(day(), '2026-10-23')!;
  assert.deepEqual(dayProgress(p), { done: 2, total: 2, state: 'complete' });
  p.tasks[0] = { ...p.tasks[0], status: 'unknown', recorded_at: null };
  assert.deepEqual(dayProgress(p), { done: 1, total: 2, state: 'in_progress' });
  p.medications[0] = { ...p.medications[0], status: 'unknown', recorded_at: null };
  assert.deepEqual(dayProgress(p), { done: 0, total: 2, state: 'none' });
});

const require = createRequire(import.meta.url);
await loadBindings();
const code = (await transform(readFileSync(new URL('../app/demo/recovery/dashboard.tsx', import.meta.url), 'utf8'), {
  filename: 'dashboard.tsx', jsc: { parser: { syntax: 'typescript', tsx: true }, transform: { react: { runtime: 'automatic' } } },
  module: { type: 'commonjs' },
})).code;
const module = { exports: {} as { RecoveryDashboard: React.ComponentType<any> } };
new Function('require', 'module', 'exports', code)((id: string) => id.startsWith('../../../lib/')
  ? require(`../lib/${id.split('/').at(-1)}.ts`) : require(id), module, module.exports);
const render = (props: object = {}) => renderToStaticMarkup(createElement(module.exports.RecoveryDashboard, {
  week: readWeekSummary(weekPayload()), day: readRecoveryDay(day(), '2026-10-23'), selected: '2026-10-23',
  loading: false, error: false, onSelect() {}, ...props,
}));

test('dashboard renders accessible date selection, medicine details, task activity and safe provenance', () => {
  const html = render();
  assert.equal((html.match(/aria-pressed=/g) || []).length, 7);
  assert.match(html, /aria-pressed="true"/); assert.match(html, /aria-current="date"/);
  assert.match(html, /1 demo tablet/); assert.match(html, /06:45/);
  assert.match(html, /Synthetic walk/); assert.match(html, /Synthetic demo history/);
  assert.match(html, /&lt;script&gt;/); assert.ok(!html.includes('<script>'));
  const p = day(); p.synthetic_demo_history = false;
  assert.ok(!render({ day: p }).includes('Synthetic demo history'));
});

test('missing historical schedules are shown honestly and previous selected-day details are hidden', () => {
  const p = day(); p.schedule_evidence = 'missing_or_conflicting'; p.medications = [];
  assert.match(render({ day: p }), /Not enough historical schedule evidence/);
  assert.ok(!render({ selected: '2026-10-20' }).includes('1 demo tablet'));
  assert.match(render({ day: null, error: true }), /role="alert"/);
});

// Saved history on Wed 21 and Thu 22, and today's own occurrences on Fri 23; nothing before.
const savedFrom21 = () => {
  const payload = weekPayload() as { week: { days: Record<string, unknown>[] } };
  payload.week.days.forEach((entry, i) => {
    entry.schedule_evidence = i < 4 ? 'missing' : i < 6 ? 'snapshot' : 'current_day_occurrences';
    if (i === 4 || i === 5) entry.status = 'completed';
  });
  return readWeekSummary(payload)!;
};

test('the calendar starts after discharge, regardless of whether history has been recorded', () => {
  for (const week of [savedFrom21(), readWeekSummary(weekPayload())!]) {
    const { past, upcoming } = calendarDays(week);
    assert.deepEqual(past.map(day => day.date), ['2026-10-21', '2026-10-22', '2026-10-23']);
    assert.deepEqual(upcoming, ['2026-10-24', '2026-10-25', '2026-10-26', '2026-10-27']);
  }
});

test('a 16 October discharge displays 17–23 October with six completed dummy days and live today', async () => {
  const payload = weekPayload(); payload.week.discharge_date = '2026-10-16';
  const week = readWeekSummary(payload)!;
  assert.equal(week.dischargeDate, '2026-10-16');
  assert.deepEqual(calendarDays(week).past.map(d => d.date), Array.from({ length: 7 }, (_, i) => `2026-10-${17 + i}`));
  assert.deepEqual(calendarDays(week).upcoming, []);
  const snapshot = await fetchRecoverySnapshot('', new AbortController().signal, async (url: any) => {
    if (String(url).includes('week-summary')) return Response.json(payload);
    const date = String(url).split('date=')[1];
    const details = day(date);
    if (date === '2026-10-23') {
      details.tasks[0].status = 'unknown'; details.tasks[0].recorded_at = null as any;
    }
    return Response.json(details);
  });
  assert.equal(snapshot.date, '2026-10-23');
  assert.equal(Object.keys(snapshot.days).length, 7);
  const html = render({ ...snapshot, selected: snapshot.date });
  assert.match(html, /Sat 17 – Fri 23/);
  assert.match(html, /<b>6\/7<\/b><p>Days completed/);
  for (let d = 17; d <= 22; d++) assert.ok(html.includes(`aria-label="2026-10-${d}, All done"`));
  assert.ok(html.includes('aria-label="2026-10-23, In progress, today"'));
});

test('missing or invalid discharge dates use the available week, and old discharges stay within seven days', () => {
  for (const discharge of [undefined, 'bad', '2026-02-30', '2026-10-01']) {
    const payload = weekPayload(); (payload.week as any).discharge_date = discharge;
    const calendar = calendarDays(readWeekSummary(payload)!);
    assert.equal(calendar.past[0].date, '2026-10-17');
    assert.equal(calendar.past.length, 7);
    assert.deepEqual(calendar.upcoming, []);
  }
});

test('the dashboard shows Wed 21 to Tue 27, days completed, and the selected day\'s tasks', () => {
  // Wed 21 all done, Thu 22 only partly done, Fri 23 (selected) all done.
  const partial = day('2026-10-22'); partial.tasks[0].status = 'unknown'; (partial.tasks[0] as any).recorded_at = null;
  const days = { '2026-10-21': readRecoveryDay(day('2026-10-21'), '2026-10-21'), '2026-10-22': readRecoveryDay(partial, '2026-10-22'),
    '2026-10-23': readRecoveryDay(day('2026-10-23'), '2026-10-23') };
  const html = render({ week: savedFrom21(), days });
  assert.match(html, /Wed 21 – Tue 27/);
  assert.match(html, /class="week-day completed"[^>]*aria-label="2026-10-21, All done"/);
  assert.match(html, /class="week-day in-progress"[^>]*aria-label="2026-10-22, In progress"/);
  assert.match(html, /✓ All done · ◐ In progress · ◌ Nothing recorded/);
  assert.ok(!html.includes('2026-10-20,'));
  assert.equal((html.match(/aria-pressed=/g) || []).length, 7);
  assert.equal((html.match(/upcoming" aria-pressed="false" disabled=""/g) || []).length, 4);
  // Out of all seven days: Wed and Fri are fully done; Thu is in progress and the four ahead are not yet.
  assert.match(html, /<b>2\/7<\/b><p>Days completed<\/p><\/div>/);
  // The selected day (Fri 23), counted like Today: its 1 task and 1 scheduled dose, both recorded done.
  assert.match(html, /<b>2\/2<\/b><p>Tasks completed<\/p>\s*<small>Fri 23<\/small>/);
  assert.ok(!html.includes('incomplete history'));
  // No day details yet: no task total is guessed.
  assert.match(render({ week: savedFrom21(), day: null }), /<b>–<\/b><p>Tasks completed/);
});

test('a dose or task with nothing recorded has no status label', () => {
  const p = day();
  Object.assign(p.medications[0], { status: 'unknown', recorded_at: null });
  const html = render({ day: p });
  assert.ok(!html.includes('Not enough evidence') && !html.includes('No confirmed record'));
  assert.match(html, /Recorded complete/); // the recorded walk keeps its label
});

test('each task says when to do it, and repeats are numbered as on the Today page', () => {
  const p = day();
  const task = (n: number, period: string | null, name = 'Knee exercises') =>
    ({ occurrence_id: `task_${n}#2026-10-23#${n}`, name, period, status: 'unknown', recorded_at: null });
  Object.assign(p, { tasks: [task(1, 'morning'), task(2, 'afternoon'), task(3, 'evening'),
    task(4, '07:30', 'Walking'), task(5, '15:00', 'Walking'), task(6, null, 'Ice pack')] });
  const html = render({ day: readRecoveryDay(p, '2026-10-23') });
  for (const line of ['Morning · 1 of 3', 'Afternoon · 2 of 3', 'Evening · 3 of 3', '07:30 · 1 of 2', '15:00 · 2 of 2']) {
    assert.ok(html.includes(line), line);
  }
  assert.match(html, /Ice pack<\/b><span class="d">Any time</);
});

test('there is no Refresh button: the page reloads its data by itself', () => {
  assert.ok(!render().includes('Refresh'));
});
