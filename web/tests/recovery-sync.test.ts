import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readToday } from '../lib/assistant-data.ts';
import { completionFingerprint, readSequence } from '../lib/recovery-sync.ts';

function today(status = 'pending', reset: string | null = null) {
  return readToday({ date: '2026-10-23', demo_reset_at: reset, tasks: [
    { occurrence_id: 'walk#2026-10-23#1', description: 'Walk', status,
      ...(status === 'completed' ? { completed_at: '2026-10-23T08:00:00+01:00' } : {}) },
  ], medications: [] });
}

test('external save, undo and reset invalidate history; unchanged polls do not', () => {
  const pending = completionFingerprint(today());
  const completed = completionFingerprint(today('completed'));
  assert.notEqual(pending, completed);
  assert.equal(pending, completionFingerprint(today()));
  assert.notEqual(completed, completionFingerprint(today('completed', '2026-10-18T12:00:00Z')));
  assert.notEqual(completed, completionFingerprint(today('pending')));
});

test('a slow pre-save poll cannot undo a newer persisted read or replace its error state', async () => {
  const sequence = readSequence();
  const old = sequence.begin();
  const fresh = sequence.begin();
  let shown = today();
  const apply = async (id: number, value: ReturnType<typeof today>) => {
    await Promise.resolve();
    if (sequence.current(id)) shown = value;
  };
  await apply(fresh, today('completed'));
  await apply(old, today('pending'));
  assert.equal(shown.items[0].done, true);
  assert.equal(sequence.current(old), false);
  assert.equal(sequence.current(fresh), true);
});
