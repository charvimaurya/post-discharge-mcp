// Verify polling identity, termination, and failure behavior without AWS.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { waitForRecoveryState, timeoutMessage } from '../lib/poll.ts';

test('ignores an old ready state and waits for this document to be ready', async () => {
  const states = [undefined, { document_id: 'old', ingestion_status: 'ready' },
    { document_id: 'new', ingestion_status: 'processing' }, { document_id: 'new', ingestion_status: 'ready' }];
  let calls = 0;
  const result = await waitForRecoveryState('new', async () => {
    const state = states[calls++]; return { found: !!state, state };
  }, new AbortController().signal, 1000, 1);
  assert.equal(result.document_id, 'new'); assert.equal(calls, 4);
});
test('reports timeout', async () => {
  await assert.rejects(waitForRecoveryState('new', async () => ({ found: false }),
    new AbortController().signal, 20, 1), { message: timeoutMessage });
});
test('stops when unmounted/aborted', async () => {
  const controller = new AbortController(); controller.abort();
  await assert.rejects(waitForRecoveryState('new', async () => { throw new Error('Should not read'); },
    controller.signal), { name: 'AbortError' });
});
test('reports read failures', async () => {
  await assert.rejects(waitForRecoveryState('new', async () => { throw new Error('Polling failed'); },
    new AbortController().signal), { message: 'Polling failed' });
});
test('reports a matching failed document', async () => {
  await assert.rejects(waitForRecoveryState('new', async () => ({ found: true,
    state: { document_id: 'new', ingestion_status: 'failed' } }), new AbortController().signal), /processing failed/);
});
