import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  MAX_UPLOAD_BYTES, UPLOADS_PER_SESSION, checkUploadFile, clearPreviousHistory, createUploadLimiter, tooLargeMessage,
  uploadLimitMessage, validateUpload, wrongDocumentMessage,
} from '../lib/upload-validation.ts';
import { demoCounters, uploadsPerSession } from '../lib/demo-limits.ts';

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

test('sends the bridge key header it is given on both bridge calls', async () => {
  const seen: Record<string, string>[] = [];
  const request = (async (_url, init) => {
    seen.push(init?.headers as Record<string, string>);
    return Response.json({ accepted: true });
  }) as typeof fetch;
  const key = { 'X-AfterWard-Key': 'test-key' };
  await validateUpload(bytes, 'http://bridge', request, 'req-1', key);
  await clearPreviousHistory('http://bridge', request, 'req-1', key);
  assert.equal(seen.length, 2);
  for (const headers of seen) {
    assert.equal(headers['X-AfterWard-Key'], 'test-key');
    assert.equal(headers['X-Request-ID'], 'req-1');
  }
});

test('the upload limit comes from DEMO_UPLOADS_PER_SESSION, else 3', () => {
  assert.equal(uploadsPerSession('10'), 10);
  assert.equal(uploadsPerSession(undefined), 3);
  for (const bad of ['', ' ', '0', '-2', '2.5', 'lots']) assert.equal(uploadsPerSession(bad), 3, bad);
  const saved = process.env.DEMO_UPLOADS_PER_SESSION;
  process.env.DEMO_UPLOADS_PER_SESSION = '7';
  try {
    const rules = demoCounters('upload', 's', 1000, 'ip', 'key', 0);
    assert.equal(rules.find(rule => rule.key === 'upload:s:s')?.limit, 7);
  } finally {
    if (saved === undefined) delete process.env.DEMO_UPLOADS_PER_SESSION; else process.env.DEMO_UPLOADS_PER_SESSION = saved;
  }
});

test('the 4th upload in one session is refused; another session is still allowed', () => {
  const uploads = createUploadLimiter(3);
  for (let n = 1; n <= 3; n += 1) {
    assert.equal(uploads.canUpload('demo-one'), true, `upload ${n}`);
    uploads.recordUpload('demo-one');
  }
  assert.equal(uploads.canUpload('demo-one'), false);
  assert.equal(uploads.canUpload('demo-two'), true);
  assert.equal(uploadLimitMessage, "You've reached the upload limit for this demo. Please try again later.");
  assert.equal(UPLOADS_PER_SESSION, 3);
});

test('only a PDF of at most 5 MB passes the file check', () => {
  const pdf = (size: number) => { const b = new Uint8Array(size); b.set([37, 80, 68, 70, 45]); return b; };
  assert.equal(checkUploadFile('letter.pdf', 'application/pdf', pdf(MAX_UPLOAD_BYTES)), null);
  assert.equal(checkUploadFile('letter.pdf', '', pdf(1024)), null);
  assert.deepEqual(checkUploadFile('letter.pdf', 'application/pdf', pdf(MAX_UPLOAD_BYTES + 1)), { status: 413, error: tooLargeMessage });
  assert.equal(checkUploadFile('letter.docx', '', pdf(1024))?.status, 400);
  assert.equal(checkUploadFile('letter.pdf', 'image/png', pdf(1024))?.status, 400);
  assert.equal(checkUploadFile('letter.pdf', 'application/pdf', new Uint8Array(1024))?.status, 400);
  assert.equal(checkUploadFile('letter.pdf', 'application/pdf', new Uint8Array(0))?.status, 400);
  assert.equal(MAX_UPLOAD_BYTES, 5 * 1024 * 1024);
});
