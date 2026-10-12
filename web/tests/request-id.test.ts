// The /api routes reuse an ID-shaped X-Request-ID and replace anything else.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { requestIdFrom } from '../lib/request-id.ts';
import { validateUpload } from '../lib/upload-validation.ts';

test('reuses an incoming request ID', () => {
  assert.equal(requestIdFrom(new Headers({ 'X-Request-ID': 'web-0123456789abcdef' }), () => 'made'), 'web-0123456789abcdef');
});

test('makes an ID when none is sent', () => {
  assert.equal(requestIdFrom(new Headers(), () => 'made-12345678'), 'made-12345678');
  assert.match(requestIdFrom(new Headers()), /^[a-f0-9]{32}$/);
});

test('never reuses a header that is not ID-shaped', () => {
  for (const sent of ['x', 'Margaret took her apixaban', 'a'.repeat(65), 'id with spaces 123']) {
    assert.equal(requestIdFrom(new Headers({ 'X-Request-ID': sent }), () => 'made-12345678'), 'made-12345678');
  }
});

test('the upload check sends the request ID to the bridge', async () => {
  let seen: Record<string, string> = {};
  const fakeFetch = (async (_url: unknown, init?: RequestInit) => {
    seen = init?.headers as Record<string, string>;
    return new Response(JSON.stringify({ accepted: true }), { status: 200 });
  }) as typeof fetch;
  const result = await validateUpload(new Uint8Array([37, 80, 68, 70]), 'http://bridge', fakeFetch, 'web-0123456789abcdef');
  assert.equal(result.accepted, true);
  assert.equal(seen['X-Request-ID'], 'web-0123456789abcdef');
});
