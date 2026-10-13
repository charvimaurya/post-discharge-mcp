import { test } from 'node:test';
import assert from 'node:assert/strict';
import { clearPreviousHistory, validateUpload, wrongDocumentMessage } from '../lib/upload-validation.ts';

const bytes = new Uint8Array([37, 80, 68, 70]);

test('rejects a wrong document before upload can proceed', async () => {
  const request = (async () => Response.json({ error: wrongDocumentMessage }, { status: 422 })) as typeof fetch;
  assert.deepEqual(await validateUpload(bytes, 'http://bridge', request),
    { accepted: false, status: 422, error: wrongDocumentMessage });
});

test('accepts only explicit approval from the bridge', async () => {
  const request = (async (url, init) => {
    assert.equal(url, 'http://bridge/documents/validate');
    assert.equal(init?.method, 'POST');
    assert.ok(init?.body instanceof Blob);
    return Response.json({ accepted: true });
  }) as typeof fetch;
  assert.deepEqual(await validateUpload(bytes, 'http://bridge', request), { accepted: true, status: 200 });
});

test('does not accept a document if validation is unavailable', async () => {
  const request = (async () => { throw new Error('offline'); }) as typeof fetch;
  assert.equal((await validateUpload(bytes, 'http://bridge', request)).accepted, false);
});

test('does not accept a malformed validation response', async () => {
  const request = (async () => Response.json({})) as typeof fetch;
  assert.equal((await validateUpload(bytes, 'http://bridge', request)).accepted, false);
});

test('asks the bridge to clear the previous history, sending nothing that names a patient', async () => {
  const request = (async (url, init) => {
    assert.equal(url, 'http://bridge/documents/uploaded');
    assert.equal(init?.method, 'POST');
    assert.equal(init?.body, undefined);
    return Response.json({ deleted: 3 });
  }) as typeof fetch;
  assert.equal(await clearPreviousHistory('http://bridge', request), true);
});

test('reports when the previous history could not be cleared', async () => {
  const failing = (async () => Response.json({ error: 'x' }, { status: 502 })) as typeof fetch;
  const offline = (async () => { throw new Error('offline'); }) as typeof fetch;
  assert.equal(await clearPreviousHistory('http://bridge', failing), false);
  assert.equal(await clearPreviousHistory('http://bridge', offline), false);
});
