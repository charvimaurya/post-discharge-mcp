// Verify when reminders are shown/spoken and that polling stops cleanly, without a browser.
import { test, mock } from 'node:test';
import assert from 'node:assert/strict';
import { loadSpokenId, planCheckin, saveSpokenId, startPolling } from '../lib/checkin.ts';

const walk = { checkin_id: '2026-10-23#task_abc#2026-10-23#1', text: 'Good morning.' };
const fresh = { shownId: null, spokenId: null, started: false };
const flush = () => new Promise(resolve => setImmediate(resolve));

test('no reminder: nothing shown or spoken', () => {
  assert.deepEqual(planCheckin(null, { ...fresh, started: true }), { show: false, speak: false });
});
test('before Start: shown but not spoken', () => {
  assert.deepEqual(planCheckin(walk, fresh), { show: true, speak: false });
});
test('after Start: a reminder shown earlier is spoken, not shown again', () => {
  assert.deepEqual(planCheckin(walk, { shownId: walk.checkin_id, spokenId: null, started: true }),
    { show: false, speak: true });
});
test('same reminder on the next poll: nothing repeats', () => {
  assert.deepEqual(planCheckin(walk, { shownId: walk.checkin_id, spokenId: walk.checkin_id, started: true }),
    { show: false, speak: false });
});
test('a new reminder is shown and spoken', () => {
  const next = { checkin_id: 'other', text: 'Time for your tablet soon.' };
  assert.deepEqual(planCheckin(next, { shownId: walk.checkin_id, spokenId: walk.checkin_id, started: true }),
    { show: true, speak: true });
});
test('spoken id storage never throws', () => {
  const blocked = { getItem() { throw new Error('blocked'); }, setItem() { throw new Error('blocked'); } };
  assert.equal(loadSpokenId(blocked), null);
  assert.doesNotThrow(() => saveSpokenId(blocked, 'x'));
  const memory = new Map<string, string>();
  const store = { getItem: (k: string) => memory.get(k) ?? null, setItem: (k: string, v: string) => { memory.set(k, v); } };
  saveSpokenId(store, 'x');
  assert.equal(loadSpokenId(store), 'x');
});

test('polls immediately, then every 5 seconds, and stops on cleanup', async () => {
  mock.timers.enable({ apis: ['setInterval'] });
  try {
    let reads = 0;
    let seenSignal: AbortSignal | undefined;
    const results: number[] = [];
    const stop = startPolling(async signal => { seenSignal = signal; return ++reads; },
      value => results.push(value), () => assert.fail('no errors expected'));
    await flush();
    assert.equal(reads, 1);
    mock.timers.tick(5_000); await flush();
    assert.equal(reads, 2);
    stop();
    assert.equal(seenSignal?.aborted, true);
    mock.timers.tick(20_000); await flush();
    assert.equal(reads, 2);
    assert.deepEqual(results, [1, 2]);
  } finally {
    mock.timers.reset();
  }
});
test('a slow read is not overlapped and its result is dropped after cleanup', async () => {
  mock.timers.enable({ apis: ['setInterval'] });
  try {
    let reads = 0;
    let finish: (value: string) => void = () => {};
    const results: string[] = [];
    const stop = startPolling(() => { reads++; return new Promise<string>(resolve => { finish = resolve; }); },
      value => results.push(value), () => {});
    mock.timers.tick(15_000); await flush();
    assert.equal(reads, 1);
    stop();
    finish('late');
    await flush();
    assert.deepEqual(results, []);
  } finally {
    mock.timers.reset();
  }
});
test('read failures are reported, not thrown', async () => {
  const errors: unknown[] = [];
  const stop = startPolling(async () => { throw new Error('offline'); }, () => {}, error => errors.push(error));
  await flush();
  stop();
  assert.equal((errors[0] as Error).message, 'offline');
});
