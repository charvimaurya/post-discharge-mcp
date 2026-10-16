import { test } from 'node:test';
import assert from 'node:assert/strict';
import { resetDemo } from '../lib/reset.ts';

test('posts to the bridge reset with the key header, request id and only the session id', async () => {
  const request = (async (url, init) => {
    assert.equal(url, 'http://bridge/reset');
    assert.equal(init?.method, 'POST');
    const headers = init?.headers as Record<string, string>;
    assert.equal(headers['X-AfterWard-Key'], 'test-key');
    assert.equal(headers['X-Request-ID'], 'req-1');
    assert.deepEqual(JSON.parse(String(init?.body)), { session_id: 'demo-abc' });
    return Response.json({ events_deleted: 2, tasks_reset: 5, medications_reset: 4 });
  }) as typeof fetch;
  assert.deepEqual(await resetDemo('http://bridge', request, 'req-1', 'demo-abc', { 'X-AfterWard-Key': 'test-key' }),
    { ok: true, status: 200 });
});

test('reports the bridge message when the reset is refused', async () => {
  for (const [status, error] of [[401, 'Not allowed.'], [409, 'No plan to reset. Upload a letter first.'], [502, 'Could not reset the demo. Please try again.']] as const) {
    const request = (async () => Response.json({ error }, { status })) as typeof fetch;
    assert.deepEqual(await resetDemo('http://bridge', request), { ok: false, status, error });
  }
});

test('reports a failure when the bridge cannot be reached', async () => {
  const request = (async () => { throw new Error('offline'); }) as typeof fetch;
  const result = await resetDemo('http://bridge', request);
  assert.equal(result.ok, false);
  assert.equal(result.status, 502);
});
