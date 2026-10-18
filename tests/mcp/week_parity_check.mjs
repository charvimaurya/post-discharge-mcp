// Give one get_week_summary result to both screens and print what each shows per day:
// the web app's reader (web/lib/week-summary.ts) and the MCP App's shipped script (today.html).
// Run with: node --experimental-strip-types tests/mcp/week_parity_check.mjs < result.json
import fs from 'node:fs';
import vm from 'node:vm';
import { readWeekSummary } from '../../web/lib/week-summary.ts';

const result = JSON.parse(fs.readFileSync(0, 'utf8'));
const data = result.structuredContent.data;

// The web app receives the fields the bridge's /week-summary route passes on (app/web_bridge.py).
const web = readWeekSummary({ week: data.week, timezone: data.timezone, as_of: data.as_of });

class Element {
  constructor() { this.children = []; this.attributes = {}; this._text = ''; this.hidden = false; this.className = ''; }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map(child => child.textContent).join(' '); }
  append(child) { this.children.push(child); }
  replaceChildren(...children) { this._text = ''; this.children = children; }
  setAttribute(key, value) { this.attributes[key] = value; }
}
const ids = ['message', 'tasks', 'count', 'progress', 'week', 'week-summary', 'week-days', 'week-synthetic', 'week-activity', 'week-activity-days'];
const elements = Object.fromEntries(ids.map(id => [id, new Element()]));
let listener;
const sent = [];
const host = { postMessage: data => sent.push(data) };
const window = { parent: host, addEventListener: (name, fn) => { listener = fn; }, removeEventListener: () => {} };
const document = { getElementById: id => elements[id], createElement: () => new Element(), documentElement: { clientWidth: 600, scrollHeight: 700 } };
const html = fs.readFileSync(new URL('../../app/mcp/ui/today.html', import.meta.url), 'utf8');
vm.runInNewContext(html.match(/<script>([\s\S]*?)<\/script>/)[1], { window, document, Intl, Date });
const receive = message => listener({ data: message, source: host, origin: 'https://host.example' });
receive({ jsonrpc: '2.0', id: sent[0].id, result: { protocolVersion: '2026-01-26', hostInfo: { name: 'Parity', version: '1' }, hostCapabilities: {}, hostContext: {} } });
receive({ jsonrpc: '2.0', method: 'ui/notifications/tool-result', params: result });

console.log(JSON.stringify({
  raw: data.week.activity.map(entry => entry.completed_tasks),
  web_tasks: web.activity.map(entry => entry.completedTasks),
  app_tasks: elements['week-activity'].hidden ? null : elements['week-activity-days'].children.map(row => Number(row.children[1].textContent)),
  web_medicines: web.days.map(day => day.status),
  app_medicines: elements['week-days'].children.map(row => row.className.split(' ')[1]),
  web_medicine_days: web.completedDays,
  app_medicine_summary: elements['week-summary'].textContent,
}));
