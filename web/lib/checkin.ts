// Decide when a polled reminder is shown or spoken, and run the /api/today poll.
export type PendingCheckin = { checkin_id: string; text: string; [field: string]: unknown };
export type TodayResponse = { pending_checkin?: PendingCheckin | null };
export type CheckinMemory = { shownId: string | null; spokenId: string | null; started: boolean };

export const CHECKIN_POLL_MS = 5_000;
const SPOKEN_KEY = 'afterward.lastSpokenCheckinId';

// Show each reminder once; speak it once, and only after Start.
export function planCheckin(pending: PendingCheckin | null | undefined, memory: CheckinMemory) {
  if (!pending?.checkin_id || !pending.text) return { show: false, speak: false };
  return {
    show: pending.checkin_id !== memory.shownId,
    speak: memory.started && pending.checkin_id !== memory.spokenId,
  };
}

// The last spoken reminder survives a reload within this browser session.
export function loadSpokenId(storage: Pick<Storage, 'getItem'> | undefined): string | null {
  try { return storage?.getItem(SPOKEN_KEY) ?? null; } catch { return null; }
}

export function saveSpokenId(storage: Pick<Storage, 'setItem'> | undefined, id: string): void {
  try { storage?.setItem(SPOKEN_KEY, id); } catch { /* memory-only is fine */ }
}

// Read now and then every interval, never overlapping. Returns a stop function.
export function startPolling<T>(
  read: (signal: AbortSignal) => Promise<T>,
  onResult: (value: T) => void,
  onError: (error: unknown) => void,
  intervalMs = CHECKIN_POLL_MS,
): () => void {
  const controller = new AbortController();
  let running = false;

  const tick = async () => {
    if (running || controller.signal.aborted) return;
    running = true;
    try {
      const value = await read(controller.signal);
      if (!controller.signal.aborted) onResult(value);
    } catch (error) {
      if (!controller.signal.aborted) onError(error);
    } finally {
      running = false;
    }
  };

  void tick();
  const timer = setInterval(tick, intervalMs);
  return () => { clearInterval(timer); controller.abort(); };
}
