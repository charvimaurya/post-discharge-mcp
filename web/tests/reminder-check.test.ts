// The /demo page asks for a reminder check before it reads /today. No network.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { checkThenLoad, startReminderChecks } from '../lib/reminder-check.ts';

const wait = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

test('the check runs before today is read', async () => {
  const order: string[] = [];
  const result = await checkThenLoad(
    async () => { order.push('check'); },
    async () => { order.push('load'); return 'today'; },
  );
  assert.deepEqual(order, ['check', 'load']);
  assert.equal(result, 'today');
});

test('today is still read when the check fails', async () => {
  const order: string[] = [];
  await checkThenLoad(
    async () => { order.push('check'); throw new Error('bridge down'); },
    async () => { order.push('load'); },
  );
  assert.deepEqual(order, ['check', 'load']);
});

test('checks at once, repeats on the interval, and stops', async () => {
  const order: string[] = [];
  const stop = startReminderChecks(
    async () => { order.push('check'); },
    async () => { order.push('load'); },
    20,
  );
  await wait(5);
  assert.deepEqual(order, ['check', 'load']);
  await wait(40);
  assert.ok(order.length >= 4, `expected a repeat, got ${order.join(',')}`);
  stop();
  const afterStop = order.length;
  await wait(50);
  assert.equal(order.length, afterStop);
});
