import type { Today } from './assistant-data.ts';

/** Ignore superseded reads (a poll may finish after a post-save refresh). */
export function readSequence() {
  let latest = 0;
  return { begin: () => ++latest, current: (request: number) => request === latest };
}

/** Invalidate history after external saves/undo/reset, without scanning it each poll. */
export function completionFingerprint(today: Today): string {
  return JSON.stringify([today.date, today.resetAt,
    today.items.map(item => [item.id, item.done, item.doneAt]).sort((a, b) => String(a[0]).localeCompare(String(b[0])))]);
}
