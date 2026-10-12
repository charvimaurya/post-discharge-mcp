// Ask for a reminder check, then read today's plan, so a new reminder shows (and is spoken) at once.
// On AWS the EventBridge schedule runs the same check; locally the /demo page asks while it is open.

export const REMINDER_CHECK_MS = 60_000;

// One check, then one read. A failed check is not shown: the read still runs, and the next check retries.
export async function checkThenLoad<T>(check: () => Promise<unknown>, load: () => Promise<T>): Promise<T> {
  try { await check(); } catch { /* the next check retries */ }
  return load();
}

// Check now, then every interval, never overlapping. Returns a stop function.
export function startReminderChecks(
  check: () => Promise<unknown>,
  load: () => Promise<unknown>,
  intervalMs = REMINDER_CHECK_MS,
): () => void {
  let stopped = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const tick = async () => {
    await checkThenLoad(check, load);
    if (!stopped) timer = setTimeout(tick, intervalMs);
  };
  void tick();
  return () => { stopped = true; clearTimeout(timer); };
}
