import { test } from 'node:test';
import assert from 'node:assert/strict';
import { boundedRequest, clientAddress, demoCounters, demoIdentity, memoryCounters } from '../lib/demo-limits.ts';
const key = 'test-only-demo-key-01234567890123456789';
const now = 1792224000;
const request = (cookie?: string) => new Request('https://demo.example', { headers: cookie ? { Cookie: cookie } : {} });

test('signed session is stable; forged, expired or rotated cookies get a fresh identity', () => {
  const first = demoIdentity(request(), key, now, true);
  assert.match(first.cookie, /HttpOnly; SameSite=Lax.*Secure/);
  assert.equal(demoIdentity(request(first.cookie), key, now + 1, true).session, first.session);
  for (const [cookie, secret, time] of [[first.cookie.replace(first.session, 'a'.repeat(48)), key, now], [first.cookie, key, now + 86401], [first.cookie, 'rotated-key', now]] as const) {
    assert.notEqual(demoIdentity(request(cookie), secret, time, true).session, first.session);
  }
});

test('chat permits exactly 30/session/hour and resets at a new UTC hour', async () => {
  const consume = memoryCounters();
  for (let i = 0; i < 30; i++) assert.equal(await consume(demoCounters('chat', 's', now + 86400, 'ip', key, now), now), true);
  assert.equal(await consume(demoCounters('chat', 's', now + 86400, 'ip', key, now), now), false);
  assert.equal(await consume(demoCounters('chat', 's', now + 86400, 'ip', key, now + 3600), now + 3600), true);
});

test('IP cap is shared across sessions and concurrent calls cannot exceed 100', async () => {
  const consume = memoryCounters();
  const results = await Promise.all(Array.from({ length: 140 }, (_, i) => consume(demoCounters('chat', `s${i}`, now + 86400, 'shared-ip', key, now), now)));
  assert.equal(results.filter(Boolean).length, 100);
});

test('upload lifetime cap is three; reset and IP quotas cannot be bypassed with new sessions', async () => {
  const consume = memoryCounters();
  for (let i = 0; i < 3; i++) assert.equal(await consume(demoCounters('upload', 's', now + 86400, 'ip', key, now), now), true);
  assert.equal(await consume(demoCounters('upload', 's', now + 86400, 'ip', key, now + 3600), now + 3600), false);
  const other = memoryCounters();
  for (let i = 0; i < 10; i++) assert.equal(await other(demoCounters('upload', `s${i}`, now + 86400, 'ip', key, now), now), true);
  assert.equal(await other(demoCounters('upload', 'another', now + 86400, 'ip', key, now), now), false);
});

test('blocked multi-counter operation consumes none of its other counters', async () => {
  const consume = memoryCounters();
  await consume([{ key: 'full', limit: 1, expires: now + 10 }], now);
  assert.equal(await consume([{ key: 'free', limit: 1, expires: now + 10 }, { key: 'full', limit: 1, expires: now + 10 }], now), false);
  assert.equal(await consume([{ key: 'free', limit: 1, expires: now + 10 }], now), true);
});

test('production IP selection requires an explicit trusted proxy chain and ignores spoofed leading addresses', () => {
  const req = new Request('https://demo.example', { headers: { 'X-Forwarded-For': '1.2.3.4, 203.0.113.7' } });
  assert.equal(clientAddress(req, true, '1'), '203.0.113.7');
  assert.throws(() => clientAddress(req, true)); assert.throws(() => clientAddress(request(), true, '1'));
});

test('streaming body cap rejects undeclared/false-length oversized bodies before parsing', async () => {
  for (const headers of [{}, { 'Content-Length': '1' }] as Record<string, string>[]) {
    const req = new Request('https://demo.example', { method: 'POST', headers, body: new Uint8Array(101) });
    await assert.rejects(boundedRequest(req, 100), RangeError);
  }
  const accepted = await boundedRequest(new Request('https://demo.example', { method: 'POST', body: 'small' }), 100);
  assert.equal(await accepted.text(), 'small');
});

test('shared counter adapter uses one atomic conditional transaction and distinguishes limits from outages', async () => {
  const { distributedConsume } = await import('../lib/demo-counter-store.ts');
  const rules = demoCounters('chat', 'session', now + 86400, 'ip', key, now);
  assert.equal(await distributedConsume(rules, 'limits', async command => {
    assert.equal(command.input.TransactItems?.length, 2);
    for (const update of command.input.TransactItems || []) {
      assert.equal(update.Update?.TableName, 'limits');
      assert.match(update.Update?.ConditionExpression || '', /#count < :limit/);
    }
  }), true);
  assert.equal(await distributedConsume(rules, 'limits', async () => {
    throw { name: 'TransactionCanceledException', CancellationReasons: [{ Code: 'ConditionalCheckFailed' }] };
  }), false);
  for (const error of [{ name: 'AccessDeniedException' }, { name: 'TransactionCanceledException', CancellationReasons: [{ Code: 'TransactionConflict' }] }]) {
    await assert.rejects(distributedConsume(rules, 'limits', async () => { throw error; }), /unavailable/);
  }
});


test('manual reset shares the upload reset quota instead of resetting abuse counters', async () => {
  const consume = memoryCounters();
  const session = 'test-reset-session';
  for (let i = 0; i < 3; i++) {
    assert.equal(await consume(demoCounters('upload', session, now + 86400, '203.0.113.1', key, now), now), true);
  }
  assert.equal(await consume(demoCounters('reset', session, now + 86400, '203.0.113.1', key, now), now), false);
});
