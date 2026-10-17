// The Alexa conversation on /demo: what she says to the Echo and what AfterWard says back,
// shown as it happens. Text only: these turns are never spoken by the page.
import { readChat, type ChatReply } from './assistant-data.ts';

// source, tool_trace, help and crisis are the turn's fields as the bridge's /chat returns them.
// kind: 'launch' for the greeting when she opens the skill ("Alexa, open after ward").
export type FeedEntry = { id: number; said: string; reply: string; source?: unknown; tool_trace?: unknown; help?: unknown; crisis?: boolean; kind?: string };

const same = (a: string, b: string) => a.replace(/\s+/g, ' ').trim() === b.replace(/\s+/g, ' ').trim();

// The bubbles to add for one Alexa turn, given the latest message on screen. A greeting is
// AfterWard's alone (no "You said"), and is not added again when the same words are already
// the latest message (the page's own greeting or reminder, or the last time she opened the skill).
export function feedBubbles(entry: FeedEntry, latest?: { who: string; text: string }): { said: boolean; reply: boolean } {
  if (entry.kind !== 'launch') return { said: true, reply: true };
  const repeat = !!latest && latest.who === 'aw' && same(latest.text, entry.reply);
  return { said: false, reply: !repeat };
}
export type FeedTurn = { who: 'you' | 'aw'; text: string; via: 'alexa' };

// The Alexa reply read exactly as a web chat reply is, so the screen shows it the same way.
export function feedReply(entry: FeedEntry): ChatReply {
  return readChat({ response: entry.reply, tool_trace: entry.tool_trace, source: entry.source, help: entry.help });
}

export const FEED_POLL_MS = 2000;

// The bridge's answer, or null when it is not one (the feed is off, or the route failed).
export function readFeed(data: unknown): { turns: FeedEntry[]; latest: number } | null {
  if (!data || typeof data !== 'object') return null;
  const { turns, latest } = data as { turns?: unknown; latest?: unknown };
  if (!Array.isArray(turns) || typeof latest !== 'number') return null;
  const entries = turns.filter((t): t is FeedEntry => !!t && typeof t === 'object'
    && typeof t.id === 'number' && typeof t.said === 'string' && typeof t.reply === 'string');
  return { turns: entries, latest };
}

// Each Alexa turn as a pair of bubbles: what she said, then AfterWard's reply.
export function feedTurns(entries: FeedEntry[]): FeedTurn[] {
  return entries.flatMap(e => [
    { who: 'you' as const, text: e.said, via: 'alexa' as const },
    { who: 'aw' as const, text: e.reply, via: 'alexa' as const },
  ]);
}

// Only the web chat's own turns are ever spoken; an Alexa turn was already spoken by the Echo.
export function speakable(turn: { via?: string }): boolean {
  return turn.via !== 'alexa';
}

type Page = { hidden: boolean; addEventListener(type: 'visibilitychange', fn: () => void): void;
  removeEventListener(type: 'visibilitychange', fn: () => void): void };

// Polls every `every` ms. The first read only learns the latest id, so turns from before the page
// opened are not shown. Nothing is fetched while the tab is hidden; it carries on when it is shown
// again. A failed read (route down, feed off) shows nothing and polling goes on. Returns stop().
export function startAlexaFeed(options: {
  fetchFeed: (after: number | null) => Promise<unknown>;
  onEntries: (entries: FeedEntry[]) => void;
  page?: Page;
  every?: number;
}): () => void {
  const { fetchFeed, onEntries, page, every = FEED_POLL_MS } = options;
  let latest: number | null = null;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let reading = false;
  let stopped = false;

  const tick = async () => {
    timer = undefined;
    if (stopped || reading || page?.hidden) return;
    reading = true;
    try {
      const feed = readFeed(await fetchFeed(latest));
      if (feed && !stopped) {
        if (latest !== null && feed.latest >= latest) {
          const fresh = feed.turns.filter(t => t.id > (latest as number));
          if (fresh.length) onEntries(fresh);
        }
        // A restarted bridge counts from 0 again: follow it, or its next turns would be missed.
        latest = feed.latest;
      }
    } catch { /* Nothing on screen: the feed is extra. */ }
    reading = false;
    if (!stopped && !page?.hidden) timer = setTimeout(tick, every);
  };

  const onVisibility = () => { if (!page?.hidden && timer === undefined) void tick(); };
  page?.addEventListener('visibilitychange', onVisibility);
  void tick();

  return () => {
    stopped = true;
    if (timer !== undefined) clearTimeout(timer);
    page?.removeEventListener('visibilitychange', onVisibility);
  };
}
