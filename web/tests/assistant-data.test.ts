// Checks that the bridge replies are read correctly. No AWS, no network.
// The sample data uses the real field names from app/web_bridge.py, app/database/recovery_state.py,
// app/agent/service.py (tool_trace) and app/agent/evidence.py (source).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { answerChoices, daysAtHome, emergencyNumber, replyPoints, reprompt, letterBlocks, readChat, readToday, shortTaskLabel, splitClock, prettyTime, wasReset } from '../lib/assistant-data.ts';

const WALK_1 = 'task_walk#2026-10-23#1';

const today = {
  clock_label: 'Friday 23 October, 07:00',
  date: '2026-10-23',
  discharge_date: '2026-10-16',
  tasks: [
    { occurrence_id: WALK_1, task_id: 'task_walk', description: 'Short walk', time_of_day_label: 'morning',
      clock_time: '07:30', status: 'pending', occurrence_number: 1, occurrence_total: 2 },
    { occurrence_id: 'task_walk#2026-10-23#2', task_id: 'task_walk', description: 'Short walk', time_of_day_label: 'afternoon',
      clock_time: '15:00', status: 'pending', occurrence_number: 2, occurrence_total: 2 },
  ],
  medications: [
    { occurrence_id: 'med_para#2026-10-23#1', medication_id: 'med_para', name: 'Paracetamol', dose: '2 tablets',
      time_of_day_label: 'morning', status: 'completed', completed_at: '2026-10-23T06:50:00+00:00',
      source: { document_id: 'doc', snippet: 'Take the morning dose after breakfast.', page: 1 } },
    { occurrence_id: 'med_cod#2026-10-23#1', medication_id: 'med_cod', name: 'Codeine', as_needed: true, status: 'pending' },
  ],
  pending_checkin: {
    checkin_id: `2026-10-23#${WALK_1}`, occurrence_id: WALK_1, item_type: 'task', date: '2026-10-23',
    clock_time: '07:30', text: 'Good morning, Margaret.', created_at: '2026-10-23T07:00:00+01:00',
  },
};

test('reads tasks and medicines together, leaving out as-needed medicines', () => {
  const t = readToday(today);
  assert.equal(t.items.length, 3);
  assert.equal(t.items.filter(i => i.done).length, 1);
  assert.equal(t.items.find(i => i.kind === 'medicine')?.title, 'Paracetamol, 2 tablets');
  assert.equal(t.items.find(i => i.kind === 'task')?.name, 'Short walk');
});

test('reads the request ID of a chat turn, or null from an older bridge', () => {
  assert.equal(readChat({ response: 'Hello', tool_trace: [], request_id: 'abc12345def' }).requestId, 'abc12345def');
  assert.equal(readChat({ response: 'Hello', tool_trace: [] }).requestId, null);
});

test('task cards get a short label; the full sentence stays as the name', () => {
  const walk = 'Walking: one short walk of 5 to 10 minutes, twice a day, using your walking frame.';
  const knee = 'Knee exercises from your physiotherapy sheet: three times a day (morning, afternoon, evening).';
  assert.equal(shortTaskLabel(walk), 'Walk');
  assert.equal(shortTaskLabel(knee), 'Knee exercises');
  assert.equal(shortTaskLabel('Ice pack on the knee for 20 minutes, after exercises.'), 'Ice pack on the knee');
  const t = readToday({ tasks: [{ occurrence_id: 'task_knee#2026-10-23#1', description: knee, status: 'pending' }] });
  assert.equal(t.items[0].title, 'Knee exercises');
  assert.equal(t.items[0].name, knee);
});

test('reads completion time, letter quote and page', () => {
  const para = readToday(today).items.find(i => i.kind === 'medicine');
  assert.equal(para?.doneAt, '2026-10-23T06:50:00+00:00');
  assert.equal(para?.quote, 'Take the morning dose after breakfast.');
  assert.equal(para?.page, 1);
});

test('numbers repeated items: walk 1 of 2', () => {
  const walk = readToday(today).items.find(i => i.id === WALK_1);
  assert.deepEqual(walk?.repeat, { index: 1, total: 2, doneInGroup: 0 });
  assert.equal(walk?.clockTime, '07:30');
  assert.equal(walk?.slot, 'Morning');
});

test('reads the reminder and which item it is for', () => {
  assert.deepEqual(readToday(today).pendingCheckin,
    { id: `2026-10-23#${WALK_1}`, text: 'Good morning, Margaret.', itemId: WALK_1 });
});

test('no reminder when pending_checkin is null', () => {
  assert.equal(readToday({ ...today, pending_checkin: null }).pendingCheckin, null);
});

test('day at home comes from the server date and the discharge date', () => {
  const t = readToday(today);
  assert.equal(daysAtHome(t.date, t.dischargeDate), 7);
  assert.equal(daysAtHome(null, '2026-10-16'), null);
});

test('splits the clock label for the top bar', () => {
  assert.deepEqual(splitClock('Friday 23 October, 07:00'), { day: 'Friday 23 October', time: '7:00 am' });
  assert.equal(prettyTime('15:00'), '3:00 pm');
});

test('reads a chat reply with tool calls and a letter passage', () => {
  const r = readChat({
    response: 'Your letter says…',
    session_id: 's1',
    tool_trace: [
      { tool: 'search_discharge_instructions', arguments: { query: 'driving' }, ok: true },
      { tool: 'get_recovery_plan', arguments: {}, ok: true },
    ],
    source: { document_id: 'doc', page: 1, chunk_id: 'c1',
      passage: 'What you must not do\nDo not drive until your consultant has reviewed you.\nDo not kneel.',
      highlighted_line: 'Do not drive until your consultant has reviewed you.' },
  });
  assert.equal(r.text, 'Your letter says…');
  assert.deepEqual(r.tools.map(t => [t.name, t.kind, t.result]),
    [['search_discharge_instructions', 'read', 'ok'], ['get_recovery_plan', 'read', 'ok']]);
  assert.equal(r.saved, false);
  assert.equal(r.source?.page, 1);
  // An older reply (raw passage): the matching line is still marked.
  assert.deepEqual(letterBlocks(r.source!).map(b => b.segments.some(seg => seg.mark)), [false, true, false]);
});

test('saved is true only when a report_* tool succeeded', () => {
  const ok = readChat({ response: 'Well done.', tool_trace: [{ tool: 'report_task_completed', arguments: { occurrence_id: WALK_1 }, ok: true }] });
  const failed = readChat({ response: 'Sorry.', tool_trace: [{ tool: 'report_task_completed', arguments: {}, ok: false }] });
  assert.equal(ok.saved, true);
  assert.equal(ok.tools[0].kind, 'write');
  assert.equal(failed.saved, false);
  assert.equal(failed.tools[0].result, 'failed');
});

test('a reply with no source has no letter passage', () => {
  assert.equal(readChat({ response: 'Lovely.', tool_trace: [], source: null }).source, null);
});

test('a walk with a clock time but no time-of-day word is grouped by its time', () => {
  const t = readToday({ ...today, tasks: [
    { occurrence_id: 'task_w#2026-10-23#1', description: 'Walking: one short walk', time_of_day_label: null, clock_time: '07:30', status: 'pending' },
    { occurrence_id: 'task_w#2026-10-23#2', description: 'Walking: one short walk', time_of_day_label: null, clock_time: '15:00', status: 'pending' },
    { occurrence_id: 'task_ice#2026-10-23#1', description: 'Ice pack', time_of_day_label: null, clock_time: null, status: 'pending' },
  ] });
  assert.deepEqual(t.items.filter(i => i.kind === 'task').map(i => i.slot), ['Morning', 'Afternoon', 'Any time']);
});

test('a write held back after "not yet" shows as not recorded, and nothing is saved', () => {
  const r = readChat({ response: "That's okay, Margaret.", tool_trace: [
    { tool: 'report_medication_taken', arguments: {}, ok: false, blocked: true, note: 'Not recorded: she said she has not done it yet.' },
  ] });
  assert.equal(r.tools[0].result, 'not recorded');
  assert.equal(r.saved, false);
});

test('readChat keeps the clean excerpt: page, section, text and highlight', () => {
  const r = readChat({ response: 'Your letter says to take the morning dose after breakfast.', tool_trace: [], source: {
    document_id: 'doc', page: 1, chunk_id: 'c1', section: 'Medicines',
    text: '3. Apixaban 2.5 mg tablets. Take 1 tablet twice a day (morning and evening). Take the morning dose after breakfast. Continue as directed.',
    highlight: 'Take the morning dose after breakfast.',
    passage: 'akfast.\n2.\nCodeine ...', highlighted_line: 'Apixaban 2.5 mg tablets. ...',
  } });
  assert.equal(r.source?.section, 'Medicines');
  assert.equal(r.source?.page, 1);
  assert.equal(r.source?.highlight, 'Take the morning dose after breakfast.');
  assert.ok(r.source?.text.startsWith('3. Apixaban'));
});

test('the answering sentence is marked inside a numbered item', () => {
  const blocks = letterBlocks({ text: '3. Apixaban 2.5 mg tablets. Take the morning dose after breakfast. Continue as directed.',
    highlight: 'Take the morning dose after breakfast.', page: 1, section: 'Medicines' });
  assert.equal(blocks.length, 1);
  assert.equal(blocks[0].kind, 'item');
  assert.equal(blocks[0].number, '3');
  assert.deepEqual(blocks[0].segments.filter(s => s.mark).map(s => s.text), ['Take the morning dose after breakfast.']);
  assert.equal(blocks[0].segments.map(s => s.text).join(''), 'Apixaban 2.5 mg tablets. Take the morning dose after breakfast. Continue as directed.');
});

test('a "- " line is a bullet', () => {
  const blocks = letterBlocks({ text: '- Do not drive until it is safe.', highlight: 'Do not drive until it is safe.', page: 1, section: 'Restrictions' });
  assert.equal(blocks[0].kind, 'bullet');
  assert.equal(blocks[0].segments[0].mark, true);
});

test('an older reply without section or text still works', () => {
  const r = readChat({ response: 'Your letter says…', tool_trace: [], source: { page: 2, passage: 'Line one.\nDo not kneel.', highlighted_line: 'Do not kneel.' } });
  assert.equal(r.source?.section, null);
  assert.equal(r.source?.text, 'Line one.\nDo not kneel.');
  assert.deepEqual(letterBlocks(r.source!).map(b => b.segments.some(seg => seg.mark)), [false, true]);
});

test('reads the server opening greeting on an empty day', () => {
  const t = readToday({ opening_greeting: 'Good morning, Margaret.', tasks: [], medications: [], pending_checkin: null });
  assert.equal(t.openingGreeting, 'Good morning, Margaret.');
  assert.equal(t.pendingCheckin, null);
  assert.deepEqual(t.items, []);
  assert.equal(readToday({}).openingGreeting, '');
});

test('a source carries the related appointment line, and has none when the server sends none', () => {
  const line = 'Consultant review: Monday 23 November 2026, 9:15 am, Orthopaedic Clinic.';
  const withRelated = readChat({ response: 'x', tool_trace: [],
    source: { page: 1, text: 'Do not drive.', highlight: 'Do not drive.', related: [{ text: line, page: 2 }, { text: '' }, 'junk'] } });
  assert.deepEqual(withRelated.source?.related, [{ text: line, page: 2 }]);
  const without = readChat({ response: 'x', tool_trace: [], source: { page: 1, text: 'Do not drive.', highlight: 'Do not drive.' } });
  assert.deepEqual(without.source?.related, []);
});

test('a source carries the note for an open question in the letter, or none', () => {
  const note = { flag: 'Needs confirmation: the letter gives no end date', text: 'Only the end date is unanswered.' };
  const base = { page: 1, text: '3. Apixaban 2.5 mg tablets.', highlight: 'Apixaban 2.5 mg tablets.' };
  assert.deepEqual(readChat({ response: 'x', tool_trace: [], source: { ...base, note } }).source?.note, note);
  assert.equal(readChat({ response: 'x', tool_trace: [], source: base }).source?.note, null);
  assert.equal(readChat({ response: 'x', tool_trace: [], source: { ...base, note: { text: 'no flag' } } }).source?.note, null);
});

test('the upload screen names the patient from the letter, or says "The discharge letter"', async () => {
  const { readPlan, letterTitle } = await import('../lib/assistant-data.ts');
  assert.equal(readPlan({ first_name: 'Leo' }).firstName, 'Leo');
  assert.equal(readPlan({ first_name: '  ' }).firstName, null);
  assert.equal(readPlan({}).firstName, null);
  assert.equal(letterTitle('Margaret'), "Margaret's discharge letter");
  assert.equal(letterTitle(null), 'The discharge letter');
});

test('the Today screen gets the first name of the patient whose plan it is', () => {
  assert.equal(readToday({ first_name: 'Margaret' }).firstName, 'Margaret');
  assert.equal(readToday({ first_name: null }).firstName, null);
  assert.equal(readToday({}).firstName, null);
});

test('answerChoices turns the which-medicine question into buttons', () => {
  assert.deepEqual(answerChoices('Your paracetamol, your blood thinner, or both?'), [
    { label: 'Paracetamol', say: 'my paracetamol' },
    { label: 'Blood thinner', say: 'my blood thinner' },
    { label: 'Both', say: 'both' },
  ]);
  assert.deepEqual(answerChoices('Your paracetamol, your blood thinner, or both?').map(c => c.label),
    ['Paracetamol', 'Blood thinner', 'Both']);
  assert.deepEqual(answerChoices('Your aspirin, your ticagrelor, your statin, or all of them?').map(c => c.say),
    ['my aspirin', 'my ticagrelor', 'my statin', 'all of them']);
  assert.deepEqual(answerChoices('Which one did you take: your paracetamol or your blood thinner?'), []);
  assert.deepEqual(answerChoices('Next is your walk. Shall we go, or both?'), []);
});

test('reprompt repeats the question still waiting, without what came before it', () => {
  assert.equal(reprompt([{ who: 'aw', text: 'Your paracetamol, your blood thinner, or both?' }]),
    "Sorry, I didn't catch that. Your paracetamol, your blood thinner, or both?");
  assert.equal(reprompt([{ who: 'aw', text: 'Good morning, Margaret. Have you taken them?' }]),
    "Sorry, I didn't catch that. Have you taken them?");
  assert.equal(reprompt([{ who: 'aw', text: 'Next is your walk.' }]), "Sorry, I didn't catch that. Please say it again.");
  assert.equal(reprompt([{ who: 'you', text: 'what?' }]), "Sorry, I didn't catch that. Please say it again.");
  assert.equal(reprompt([]), "Sorry, I didn't catch that. Please say it again.");
});

test('a long reply is one point per sentence; a short opener stays with the next one', () => {
  const reply = "Thank you, Priya. I've marked your prednisolone, 8 tablets (40 mg), your fostair, 2 puffs, and your omeprazole, 1 capsule, as taken. "
    + 'Your prednisolone is for 5 more days. Your Fostair is to take every day, even when you feel well.';
  assert.deepEqual(replyPoints(reply), [
    "Thank you, Priya. I've marked your prednisolone, 8 tablets (40 mg), your fostair, 2 puffs, and your omeprazole, 1 capsule, as taken.",
    'Your prednisolone is for 5 more days.',
    'Your Fostair is to take every day, even when you feel well.',
  ]);
  assert.deepEqual(replyPoints('Your paracetamol, your blood thinner, or both?'), ['Your paracetamol, your blood thinner, or both?']);
  assert.deepEqual(replyPoints('Thank you. Next is your walk.'), ['Thank you. Next is your walk.']);
});

test("the help card calls the letter's emergency number, or 999 when it gives none", () => {
  assert.equal(emergencyNumber([
    { urgency: 'contact_care_team', action: 'Call the ward on 0000 000 000 (fictional number)' },
    { urgency: 'emergency', action: 'Call emergency services straight away: 555-555-0199' },
  ]), '555-555-0199');
  assert.equal(emergencyNumber([{ urgency: 'emergency', action: 'Call emergency services straight away' }]), null);
  assert.equal(emergencyNumber([{ urgency: 'contact_care_team', action: 'Ward: 0000 000 001' }]), null);
});

test('a related line keeps its own heading, such as the emergency number', () => {
  const r = readChat({ response: 'x', tool_trace: [], source: { page: 2, text: 'Call emergency services.', highlight: 'Call emergency services.',
    related: [{ text: 'Emergency services number: 555-555-0199 (fictional number)', page: 2, label: 'Emergency number' }] } });
  assert.deepEqual(r.source?.related, [{ text: 'Emergency services number: 555-555-0199 (fictional number)', page: 2, label: 'Emergency number' }]);
});

test('readChat marks a reply refused under the demo chat limit', () => {
  assert.equal(readChat({ response: 'Limit.', tool_trace: [], rate_limited: true }).rateLimited, true);
  assert.equal(readChat({ response: 'Hello', tool_trace: [] }).rateLimited, false);
});

test('reads when the demo was last reset, and spots a new reset', () => {
  assert.equal(readToday({ demo_reset_at: '2026-10-17T15:00:00+00:00' }).resetAt, '2026-10-17T15:00:00+00:00');
  assert.equal(readToday({}).resetAt, null);
  // Opening the page is not a reset; a new time after that is.
  assert.equal(wasReset(undefined, '2026-10-17T15:00:00+00:00'), false);
  assert.equal(wasReset('2026-10-17T15:00:00+00:00', '2026-10-17T15:00:00+00:00'), false);
  assert.equal(wasReset('2026-10-17T15:00:00+00:00', '2026-10-17T16:00:00+00:00'), true);
  assert.equal(wasReset(null, '2026-10-17T16:00:00+00:00'), true);
  assert.equal(wasReset('2026-10-17T15:00:00+00:00', null), false);
});
