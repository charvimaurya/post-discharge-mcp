import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { loadBindings, transform } from 'next/dist/build/swc/index.js';
import { fetchRecoverySnapshot, readRecoveryDay, recordedTime } from '../lib/recovery-dashboard.ts';
import { readWeekSummary } from '../lib/week-summary.ts';

function day(date = '2026-10-23') {
  return { kind: 'recovery_day_details', schema_version: 1, date, timezone: 'Europe/London',
    scope: 'all_scheduled', schedule_evidence: 'snapshot', synthetic_demo_history: true,
    medications: [{ occurrence_id: `a#${date}#1`, name: '<script>unsafe</script>', dose: '1 demo tablet',
      period: 'morning', due_at: `${date}T06:30:00+01:00`, status: 'taken', recorded_at: `${date}T06:45:00+01:00` }],
    tasks: [{ occurrence_id: `walk#${date}#1`, name: 'Synthetic walk', status: 'completed', recorded_at: `${date}T06:50:00+01:00` }] };
}
const weekPayload = () => ({ week: { days: Array.from({ length: 7 }, (_, i) => ({ date: `2026-10-${17 + i}`,
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

test('refresh reads the selected date and sees updated persisted results without patient selectors', async () => {
  let count = 0;
  const urls: string[] = [];
  const fetcher = async (url: any, init?: RequestInit) => {
    urls.push(String(url)); assert.equal(init?.cache, 'no-store');
    if (String(url).includes('week-summary')) return Response.json(weekPayload());
    const p = day('2026-10-20'); p.medications[0].status = count++ ? 'taken' : 'unknown';
    if (count === 1) p.medications[0].recorded_at = null as any;
    return Response.json(p);
  };
  const signal = new AbortController().signal;
  assert.equal((await fetchRecoverySnapshot('2026-10-20', signal, fetcher)).day.medications[0].status, 'unknown');
  assert.equal((await fetchRecoverySnapshot('2026-10-20', signal, fetcher)).day.medications[0].status, 'taken');
  assert.deepEqual(urls, ['/api/week-summary', '/api/recovery-day?date=2026-10-20', '/api/week-summary', '/api/recovery-day?date=2026-10-20']);
  await assert.rejects(fetchRecoverySnapshot('', signal, async () => Response.json({}, { status: 502 })));
});

test('date selection outside the displayed window falls back to today', async () => {
  const result = await fetchRecoverySnapshot('1900-01-01', new AbortController().signal,
    async (url: any) => Response.json(String(url).includes('week-summary') ? weekPayload() : day()));
  assert.equal(result.date, '2026-10-23');
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
  loading: false, error: false, onSelect() {}, onRefresh() {}, ...props,
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
