// What AfterWard has already said aloud in this browser tab, so a reload shows it again but does
// not speak it twice. Reminders are remembered by checkin_id; the list is cleared when /today
// reports no reminder (she replied, its window ended, or the patient was reset), so the next
// reminder with that ID is spoken again. The opening greeting is remembered by its own words.

type Store = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;

const CHECKINS_KEY = 'afterward-spoken-checkins';
const OPENING_KEY = 'afterward-spoken-opening';

function readIds(store: Store | undefined): string[] {
  try {
    const ids = JSON.parse(store?.getItem(CHECKINS_KEY) || '[]');
    return Array.isArray(ids) ? ids.filter(id => typeof id === 'string') : [];
  } catch { return []; }
}

export function alreadySpoken(store: Store | undefined, checkinId: string): boolean {
  return readIds(store).includes(checkinId);
}

export function markSpoken(store: Store | undefined, checkinId: string): void {
  try { store?.setItem(CHECKINS_KEY, JSON.stringify([...new Set([...readIds(store), checkinId])])); }
  catch { /* storage blocked: it may be spoken again after a reload */ }
}

export function clearSpoken(store: Store | undefined): void {
  try { store?.removeItem(CHECKINS_KEY); } catch { /* storage blocked: nothing to clear */ }
}

// True the first time these words are offered; false on a reload that shows the same greeting.
export function shouldSpeakOpening(store: Store | undefined, text: string): boolean {
  try {
    if (store?.getItem(OPENING_KEY) === text) return false;
    store?.setItem(OPENING_KEY, text);
  } catch { /* storage blocked: speak it */ }
  return true;
}

// Opening Today from the start screen is a fresh start: whatever is waiting is spoken once more.
// Reloads that stay on Today never happen (a reload returns to the start screen), so this only
// runs on her own click.
export function forgetSpoken(store: Store | undefined): void {
  clearSpoken(store);
  try { store?.removeItem(OPENING_KEY); } catch { /* storage blocked: nothing to clear */ }
}
