import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { loadBindings, transform } from 'next/dist/build/swc/index.js';
import { readWeekSummary, weekDayLabel } from '../lib/week-summary.ts';

function fixture() {
  return { week: { completed_days: 99, synthetic_demo_history: false, days: Array.from({ length: 7 }, (_, i) => ({
    date: `2026-10-${17 + i}`, is_today: i === 6,
    status: i < 5 ? 'completed' : i === 5 ? 'missed' : 'not_yet_due',
  })) } };
}

test('weekly display counts evidence states rather than trusting a summary number', () => {
  const result = readWeekSummary(fixture())!;
  assert.equal(result.completedDays, 5);
  assert.equal(result.days.length, 7);
  assert.equal(result.days[5].symbol, '–');
  assert.equal(result.days[6].symbol, '○');
  assert.equal(result.days[6].isToday, true);
  assert.equal(weekDayLabel('2026-10-23'), 'Fri');
});

test('missing medication evidence remains unknown, never missed', () => {
  const payload = fixture();
  for (const day of payload.week.days) day.status = 'unknown';
  const result = readWeekSummary(payload)!;
  assert.equal(result.completedDays, 0);
  assert.ok(result.days.every(day => day.status === 'unknown' && day.symbol === '◌'));
});

test('empty evidenced schedules have a distinct neutral state', () => {
  const payload = fixture(); payload.week.days[0].status = 'no_scheduled_morning_doses';
  assert.equal(readWeekSummary(payload)!.days[0].symbol, '·');
});

test('malformed, duplicate, invalid or incomplete calendar days are refused', () => {
  for (const payload of [null, {}, { week: { days: [] } }]) assert.equal(readWeekSummary(payload), null);
  for (const alter of [
    (p: ReturnType<typeof fixture>) => { p.week.days[1].date = p.week.days[0].date; },
    (p: ReturnType<typeof fixture>) => { p.week.days[0].date = '2026-02-30'; },
    (p: ReturnType<typeof fixture>) => { p.week.days[0].status = '<script>'; },
    (p: ReturnType<typeof fixture>) => { p.week.days[0].is_today = true; },
  ]) {
    const payload = fixture(); alter(payload); assert.equal(readWeekSummary(payload), null);
  }
});

// Exercise actual React output without adding a browser framework or production build step.
const require = createRequire(import.meta.url);
await loadBindings();
const compiled = (await transform(readFileSync(new URL('../app/demo/week-panel.tsx', import.meta.url), 'utf8'), {
  filename: 'week-panel.tsx',
  jsc: { parser: { syntax: 'typescript', tsx: true }, transform: { react: { runtime: 'automatic' } } },
  module: { type: 'commonjs' },
})).code;
const module = { exports: {} as { WeekPanel?: React.ComponentType<any> } };
new Function('require', 'module', 'exports', compiled)((id: string) =>
  id === '../../lib/week-summary' ? require('../lib/week-summary.ts') : require(id), module, module.exports);
const WeekPanel = module.exports.WeekPanel!;
const render = (props: Record<string, unknown>) => renderToStaticMarkup(createElement(WeekPanel, {
  summary: null, loading: false, error: false, onRefresh() {}, ...props,
}));

test('weekly panel renders seven indicators, today and only evidence-backed synthetic label', () => {
  const payload = fixture();
  const html = render({ summary: readWeekSummary(payload) });
  assert.match(html, /5 of 7 mornings confirmed/);
  assert.match(html, /href="\/demo\/recovery"/);
  assert.match(html, /<details class="week-disclosure"><summary/);
  assert.ok(!/<details[^>]*\sopen(?:[\s=>])/.test(html));
  assert.equal((html.match(/<li /g) || []).length, 7);
  assert.match(html, /aria-current="date"/);
  assert.ok(!html.includes('Synthetic demo history'));
  payload.week.synthetic_demo_history = true;
  assert.match(render({ summary: readWeekSummary(payload) }), /Synthetic demo history/);
});

test('weekly panel renders loading, failure and unknown history without inventing adherence', () => {
  assert.match(render({ loading: true }), /Checking this week/);
  assert.match(render({ error: true }), /could not be checked/);
  const payload = fixture(); payload.week.days.forEach(day => { day.status = 'unknown'; });
  assert.match(render({ summary: readWeekSummary(payload) }), /Missing history does not mean a missed dose/);
});

test('task activity chart updates from saved counts independently of medicine adherence', () => {
  const payload = fixture();
  const activity = payload.week.days.map(day => ({ date: day.date, completed_tasks: 0 }));
  const input = { week: { ...payload.week, activity } };
  let summary = readWeekSummary(input)!;
  assert.equal(summary.activity?.[6].completedTasks, 0);
  assert.match(render({ summary }), /2026-10-23: 0 recovery tasks recorded complete/);
  activity[6].completed_tasks = 1;
  summary = readWeekSummary(input)!;
  const html = render({ summary });
  assert.match(html, /2026-10-23: 1 recovery tasks recorded complete/);
  assert.equal((html.match(/<meter /g) || []).length, 7);
  assert.equal(summary.completedDays, 5); // A walk never becomes medication adherence.
  activity[6].completed_tasks = -1;
  assert.equal(readWeekSummary(input)?.activity, undefined);
});
