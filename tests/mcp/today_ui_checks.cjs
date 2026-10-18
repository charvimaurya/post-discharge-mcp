// Exercise the production inline script with a minimal DOM and standard MCP Apps messages.
// No test switches or fixture data are included in the shipped HTML.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const fixture = JSON.parse(fs.readFileSync(0, 'utf8'));
const html = fs.readFileSync(path.join(__dirname, '../../app/mcp/ui/today.html'), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];

class Element {
  constructor(tag = 'div') { this.tagName = tag; this.children = []; this.attributes = {}; this._text = ''; this.hidden = false; }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map(child => child.textContent).join(' '); }
  set innerHTML(value) { throw new Error('Unsafe HTML rendering'); }
  append(child) { this.children.push(child); }
  replaceChildren(...children) { this._text = ''; this.children = children; }
  setAttribute(key, value) { this.attributes[key] = value; }
}
function start(embedded = true) {
  const elements = Object.fromEntries(['message', 'tasks', 'count', 'progress', 'week', 'week-summary', 'week-days', 'week-synthetic', 'week-activity', 'week-activity-days'].map(id => [id, new Element()]));
  elements.message.textContent = "Waiting for today's plan";
  elements.count.hidden = elements.progress.hidden = elements.week.hidden = elements['week-synthetic'].hidden = elements['week-activity'].hidden = true;
  const sent = [];
  let listener;
  const host = {postMessage: (data, origin) => sent.push({data, origin})};
  const window = {
    parent: host,
    addEventListener: (name, fn) => { listener = fn; },
    removeEventListener: () => { listener = undefined; },
  };
  if (!embedded) window.parent = window;
  const document = {getElementById: id => elements[id], createElement: tag => new Element(tag), documentElement: {clientWidth: 600, scrollHeight: 700}};
  vm.runInNewContext(script, {window, document, Intl, Date});
  const receive = (data, source = host, origin = 'https://host.example') => listener?.({data, source, origin});
  const initialize = () => receive({jsonrpc: '2.0', id: sent[0].data.id, result: {protocolVersion: '2026-01-26', hostInfo: {name: 'Test host', version: '1'}, hostCapabilities: {}, hostContext: {timeZone: 'Europe/London'}}});
  const deliver = result => receive({jsonrpc: '2.0', method: 'ui/notifications/tool-result', params: result});
  return {elements, sent, receive, initialize, deliver};
}
const checks = [];
function check(name, run) { run(); checks.push(name); }
check('direct opening preserves waiting state', () => {
  const app = start(false);
  assert.equal(app.elements.message.textContent, "Waiting for today's plan");
  assert.equal(app.sent.length, 0);
});
check('initializes with the standard app handshake', () => {
  const app = start();
  assert.equal(app.sent[0].data.method, 'ui/initialize');
  assert.equal(app.sent[0].data.params.appInfo.name, 'AfterWard Today');
  assert.equal(app.sent[0].data.params.protocolVersion, '2026-01-26');
  app.initialize();
  assert.equal(app.sent[1].data.method, 'ui/notifications/initialized');
});
check('ignores data before initialization and from other windows', () => {
  const app = start();
  app.deliver(fixture);
  assert.equal(app.elements.tasks.children.length, 0);
  app.initialize();
  app.receive({jsonrpc: '2.0', method: 'ui/notifications/tool-result', params: fixture}, {});
  assert.equal(app.elements.tasks.children.length, 0);
});
check('computes progress from the real SDK structured result', () => {
  const app = start(); app.initialize();
  const structuredContent = fixture.structuredContent || JSON.parse(fixture.content[0].text);
  app.deliver({structuredContent});
  assert.equal(app.elements.count.textContent, '1 of 4 done');
  assert.equal(app.elements.progress.value, 1);
  assert.equal(app.elements.progress.max, 4);
  assert.equal(app.elements.progress.attributes['aria-valuetext'], '1 of 4 tasks completed');
});
check('shows completion tick and converts time using the host timezone', () => {
  const app = start(); app.initialize(); app.deliver(fixture);
  const done = app.elements.tasks.children[0];
  assert.equal(done.className, 'item done');
  assert.match(done.textContent, /✓.*Done at 09:10/);
});
check('flags uncertainty and highlights only the next actionable task', () => {
  const app = start(); app.initialize(); app.deliver(fixture);
  const rows = app.elements.tasks.children;
  assert.match(rows[1].textContent, /Needs confirmation/);
  assert.equal(rows[1].className, 'item');
  assert.equal(rows[2].className, 'item next');
  assert.match(rows[2].textContent, /Next up.*Gentle exercise/);
});
check('supports the SDK JSON text fallback', () => {
  const app = start(); app.initialize(); app.deliver({content: fixture.content});
  assert.equal(app.elements.count.textContent, '1 of 4 done');
});
check('handles empty lists without inventing tasks', () => {
  const app = start(); app.initialize(); app.deliver({structuredContent: {ok: true, data: {tasks: []}}});
  assert.equal(app.elements.count.textContent, '0 of 0 done');
  assert.match(app.elements.message.textContent, /No recovery tasks/);
  assert.equal(app.elements.tasks.children.length, 0);
});
check('rejects malformed and failed results without reflecting diagnostics', () => {
  const invalid = [null, {}, {isError: true, content: [{type: 'text', text: 'private diagnostics'}]}, {structuredContent: {ok: false, error: {message: 'private diagnostics'}}}, {structuredContent: {ok: true, data: {}}}, {structuredContent: {ok: true, data: {tasks: [null]}}}, {content: [{type: 'text', text: '{broken'}]}];
  for (const result of invalid) {
    const app = start(); app.initialize(); app.deliver(result);
    assert.match(app.elements.message.textContent, /plan is unavailable/);
    assert.equal(app.elements.count.hidden, true);
    assert.doesNotMatch(app.elements.message.textContent, /private/);
  }
});
check('handles absent fields and renders hostile text as text', () => {
  const app = start(); app.initialize();
  app.deliver({structuredContent: {ok: true, data: {tasks: [{description: '<img src=x onerror=alert(1)>', status: 'pending'}, {}]}}});
  assert.match(app.elements.tasks.textContent, /<img src=x onerror=alert\(1\)>/);
  assert.match(app.elements.tasks.textContent, /Recovery task.*Status unavailable/);
});
check('replacement results clear stale tasks and errors clear previous data', () => {
  const app = start(); app.initialize(); app.deliver(fixture);
  app.deliver({structuredContent: {ok: true, data: {tasks: []}}});
  assert.equal(app.elements.tasks.children.length, 0);
  app.deliver(fixture); app.deliver(null);
  assert.equal(app.elements.tasks.children.length, 0);
});
check('rejects messages from a different origin after handshake', () => {
  const app = start(); app.initialize();
  app.receive({jsonrpc: '2.0', method: 'ui/notifications/tool-result', params: fixture}, undefined, 'https://wrong.example');
  assert.equal(app.elements.tasks.children.length, 0);
});
check('handles cancelled tools and unsupported protocol versions', () => {
  const app = start(); app.initialize(); app.deliver(fixture);
  app.receive({jsonrpc: '2.0', method: 'ui/notifications/tool-cancelled', params: {}});
  assert.equal(app.elements.tasks.children.length, 0);
  const other = start();
  other.receive({jsonrpc: '2.0', id: other.sent[0].data.id, result: {protocolVersion: 'unsupported'}});
  assert.match(other.elements.message.textContent, /unavailable/);
});
check('supports ping, size reporting, and teardown without tool writes', () => {
  const app = start(); app.initialize();
  app.receive({jsonrpc: '2.0', method: 'ping', id: 10});
  app.receive({jsonrpc: '2.0', method: 'ui/resource-teardown', id: 11});
  assert.ok(app.sent.some(item => item.data.id === 10 && item.data.result));
  assert.ok(app.sent.some(item => item.data.id === 11 && item.data.result));
  assert.ok(app.sent.some(item => item.data.method === 'ui/notifications/size-changed'));
  assert.ok(app.sent.every(item => item.data.method !== 'tools/call'));
  app.deliver(fixture);
  assert.equal(app.elements.tasks.children.length, 0);
});
const todayData = (fixture.structuredContent || JSON.parse(fixture.content[0].text)).data;
const weekDays = Array.from({length: 7}, (_, i) => ({date: `2026-10-${17 + i}`, is_today: i === 6, status: i < 5 ? 'completed' : i === 5 ? 'missed' : 'not_yet_due'}));
const weekly = {structuredContent: {ok: true, data: {kind: 'week_summary', schema_version: 1, today: {...todayData, date: '2026-10-23'}, week: {end_date: '2026-10-23', days: weekDays, synthetic_demo_history: true}}}};
check('Today alone has no weekly strip', () => {
  const app = start(); app.initialize(); app.deliver(fixture);
  assert.equal(app.elements.week.hidden, true);
});
check('weekly first renders a complete independent App', () => {
  const app = start(); app.initialize(); app.deliver(weekly);
  assert.equal(app.elements.count.textContent, '1 of 4 done');
  assert.equal(app.elements.week.hidden, false);
  assert.equal(app.elements['week-summary'].textContent, '5 of 7 days: all morning medicines taken');
  assert.equal(app.elements['week-days'].children.length, 7);
  assert.match(app.elements['week-days'].children[5].textContent, /-/);
  assert.equal(app.elements['week-days'].children[6].attributes['aria-current'], 'date');
  assert.equal(app.elements['week-synthetic'].hidden, false);
});
check('Today then week and same-date Today updates preserve separate states', () => {
  const app = start(); app.initialize(); app.deliver(fixture); app.deliver(weekly);
  app.deliver({structuredContent: {ok: true, data: {date: '2026-10-23', tasks: []}}});
  assert.equal(app.elements.count.textContent, '0 of 0 done');
  assert.equal(app.elements.week.hidden, false);
  app.deliver({structuredContent: {ok: true, data: {date: '2026-10-24', tasks: []}}});
  assert.equal(app.elements.week.hidden, true);
});
check('neutral states and provenance are explicit', () => {
  const data = JSON.parse(JSON.stringify(weekly));
  data.structuredContent.data.week.synthetic_demo_history = false;
  data.structuredContent.data.week.days[0].status = 'unknown';
  data.structuredContent.data.week.days[1].status = 'no_scheduled_morning_doses';
  const app = start(); app.initialize(); app.deliver(data);
  assert.equal(app.elements['week-synthetic'].hidden, true);
  assert.match(app.elements['week-days'].children[0].attributes['aria-label'], /Unknown/);
  assert.equal(app.elements['week-summary'].textContent, '3 of 7 days: all morning medicines taken');
});
check('malformed weekly results cannot inject labels or retain stale content', () => {
  for (const mutation of [d => d.week.days.pop(), d => d.week.days[0].status = '<img>', d => d.today = {}, d => d.week.days[0].date = '2026-02-31', d => d.schema_version = 999]) {
    const broken = JSON.parse(JSON.stringify(weekly)); mutation(broken.structuredContent.data);
    const app = start(); app.initialize(); app.deliver(weekly); app.deliver(broken);
    assert.equal(app.elements.week.hidden, true);
    assert.equal(app.elements['week-days'].children.length, 0);
    assert.match(app.elements.message.textContent, /unavailable/);
  }
});
check('weekly JSON text works in a new instance without retained Today data', () => {
  const app = start(); app.initialize(); app.deliver({content: [{type: 'text', text: JSON.stringify(weekly.structuredContent)}]});
  assert.equal(app.elements.week.hidden, false);
  assert.equal(app.elements.count.textContent, '1 of 4 done');
});
const counts = [2, 3, 1, 3, 2, 0, 1];
const withActivity = JSON.parse(JSON.stringify(weekly));
withActivity.structuredContent.data.week.activity = weekDays.map((day, i) => ({date: day.date, completed_tasks: counts[i]}));
check('task counts render per day, apart from the morning medicines', () => {
  const app = start(); app.initialize(); app.deliver(withActivity);
  const rows = app.elements['week-activity-days'].children;
  assert.equal(app.elements['week-activity'].hidden, false);
  assert.deepEqual(rows.map(row => Number(row.children[1].textContent)), counts);
  assert.match(rows[0].attributes['aria-label'], /^Sat 17: 2 recovery tasks recorded complete$/);
  assert.match(rows[6].attributes['aria-label'], /1 recovery tasks recorded complete, today$/);
  // The medicines line is computed from medicine statuses only, so the counts change nothing there.
  assert.equal(app.elements['week-summary'].textContent, '5 of 7 days: all morning medicines taken');
  assert.equal(app.elements['week-days'].children.length, 7);
});
check('missing or malformed task counts hide only the task section', () => {
  const mutations = [a => a.pop(), a => { a[0].date = '2026-10-16'; }, a => { a[2].completed_tasks = -1; },
    a => { a[3].completed_tasks = 1.5; }, a => { a[4].completed_tasks = '3'; }, a => { a[5] = null; }];
  for (const mutate of [...mutations, null]) {
    const data = JSON.parse(JSON.stringify(withActivity));
    if (mutate) mutate(data.structuredContent.data.week.activity); else delete data.structuredContent.data.week.activity;
    const app = start(); app.initialize(); app.deliver(withActivity); app.deliver(data);
    assert.equal(app.elements['week-activity'].hidden, true);
    assert.equal(app.elements['week-activity-days'].children.length, 0);
    assert.equal(app.elements.week.hidden, false);
    assert.equal(app.elements['week-days'].children.length, 7);
  }
});
check('a new day clears the task counts with the rest of the week', () => {
  const app = start(); app.initialize(); app.deliver(withActivity);
  app.deliver({structuredContent: {ok: true, data: {date: '2026-10-24', tasks: []}}});
  assert.equal(app.elements['week-activity'].hidden, true);
  assert.equal(app.elements['week-activity-days'].children.length, 0);
});
console.log(`${checks.length} UI checks passed`);
