import { test } from 'node:test';
import assert from 'node:assert/strict';
import { authenticatedBridgeHeaders } from '../lib/bridge-auth.ts';
import { validateUpload, clearPreviousHistory } from '../lib/upload-validation.ts';

test('missing bridge credentials fail closed', () => {
  for (const key of [undefined, '', '   ']) assert.throws(() => authenticatedBridgeHeaders(key));
});

test('upload validation and history reset both carry service authentication', async () => {
  const headers = authenticatedBridgeHeaders('mock-key', 'request-1234');
  const seen: string[] = [];
  const request = (async (url, init) => {
    assert.equal(new Headers(init?.headers).get('X-Bridge-Key'), 'mock-key');
    assert.equal(new Headers(init?.headers).get('X-Request-ID'), 'request-1234');
    seen.push(String(url));
    return Response.json({ accepted: true });
  }) as typeof fetch;
  assert.equal((await validateUpload(new Uint8Array([37]), 'https://bridge', request, 'request-1234', headers)).accepted, true);
  assert.equal(await clearPreviousHistory('https://bridge', request, 'request-1234', headers), true);
  assert.deepEqual(seen, ['https://bridge/documents/validate', 'https://bridge/documents/uploaded']);
});
