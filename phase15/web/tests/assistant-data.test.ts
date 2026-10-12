// Checks that the bridge replies are read correctly. No AWS, no network.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readChat, readToday, splitClock, prettyTime } from '../lib/assistant-data.ts';

const today = {
  clock_label: 'Friday 23 October, 07:00',
  tasks: [
    { occurrence_id: 'task_walk#2026-10-23#1', name: 'Short walk', time_of_day_label: 'morning', clock_time: '07:30', status: 'pending' },
    { occurrence_id: 'task_walk#2026-10-23#2', name: 'Short walk', time_of_day_label: 'afternoon', clock_time: '15:00', status: 'pending' },
  ],
  medications: [
    { occurrence_id: 'med_para#2026-10-23#1', name: 'Paracetamol', dose: '2 tablets', time_of_day_label: 'morning', status: 'completed' },
    { occurrence_id: 'med_cod', name: 'Codeine', as_needed: true },
  ],
  pending_checkin: { checkin_id: 'k1', occurrence_id: 'task_walk#2026-10-23#1', text: 'Good morning, Margaret.' },
};

test('reads tasks and medicines together, leaving out as-needed medicines', () => {
  const t = readToday(today);
  assert.equal(t.items.length, 3);
  assert.equal(t.items.filter(i => i.done).length, 1);
  assert.equal(t.items.find(i => i.kind === 'medicine')?.title, 'Paracetamol, 2 tablets');
});

test('numbers repeated items: walk 1 of 2', () => {
  const walk = readToday(today).items.find(i => i.id.endsWith('#1') && i.kind === 'task');
  assert.deepEqual(walk?.repeat, { index: 1, total: 2, doneInGroup: 0 });
});

test('reads the reminder and which item it is for', () => {
  assert.deepEqual(readToday(today).pendingCheckin, { id: 'k1', text: 'Good morning, Margaret.', itemId: 'task_walk#2026-10-23#1' });
});

test('splits the clock label for the top bar', () => {
  assert.deepEqual(splitClock('Friday 23 October, 07:00'), { day: 'Friday 23 October', time: '7:00 am' });
  assert.equal(prettyTime('15:00'), '3:00 pm');
});

test('reads a chat reply with tool calls and a letter passage', () => {
  const r = readChat({ response: 'Your letter says…', completed: true,
    tool_trace: [{ name: 'search_discharge_instructions', arguments: { query: 'driving' } }, { name: 'report_task_completed' }],
    source: { snippet: 'Do not drive.', page: 1 } });
  assert.equal(r.text, 'Your letter says…');
  assert.deepEqual(r.tools.map(t => t.kind), ['read', 'write']);
  assert.deepEqual(r.source, { text: 'Do not drive.', page: 1 });
});
