// The Alexa feed on /demo: new turns only, shown as "via Alexa", never spoken, paused when hidden.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { feedReply, feedTurns, readFeed, speakable, startAlexaFeed, type FeedEntry, type FeedTurn } from '../lib/alexa-feed.ts';
import { readChat } from '../lib/assistant-data.ts';
import { replyView } from '../lib/reply-view.ts';
import { speak } from '../lib/voice.ts';

const WALK = { id: 4, said: "I'm back from my walk", reply: 'Well done, Margaret.' };
const wait = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

function page(hidden = false) {
  const listeners: (() => void)[] = [];
  return {
    hidden,
    addEventListener: (_: 'visibilitychange', fn: () => void) => { listeners.push(fn); },
    removeEventListener: (_: 'visibilitychange', fn: () => void) => { listeners.splice(listeners.indexOf(fn), 1); },
    show() { this.hidden = false; listeners.forEach(fn => fn()); },
  };
}

test('a via Alexa bubble does not trigger speech', async () => {
  const spoken: string[] = [];
  (globalThis as Record<string, unknown>).window = { speechSynthesis: {
    speaking: false, pending: false, getVoices: () => [], cancel() {}, resume() {},
    speak(u: { text: string }) { spoken.push(u.text); },
  } };
  (globalThis as Record<string, unknown>).SpeechSynthesisUtterance = class { text: string; constructor(t: string) { this.text = t; } };

  const reads: (number | null)[] = [];
  const answers = [{ turns: [{ id: 3, said: 'old', reply: 'old' }], latest: 3 }, { turns: [WALK], latest: 4 }];
  const shown: FeedTurn[] = [];
  // As the page does: show every Alexa turn, and speak only what replyView says to speak.
  const stop = startAlexaFeed({
    fetchFeed: async after => { reads.push(after); return answers[Math.min(reads.length - 1, 1)]; },
    onEntries: entries => entries.forEach(entry => {
      shown.push(...feedTurns([entry]));
      const view = replyView(feedReply(entry), 'alexa');
      if (view.speak) void speak(view.turn.text);
    }),
    every: 5,
  });
  await wait(30);
  stop();

  // Starts from the latest id: the turn from before the page opened is not shown.
  assert.deepEqual(reads.slice(0, 2), [null, 3]);
  assert.deepEqual(shown, [
    { who: 'you', text: "I'm back from my walk", via: 'alexa' },
    { who: 'aw', text: 'Well done, Margaret.', via: 'alexa' },
  ]);
  assert.deepEqual(spoken, []);
  assert.equal(speakable({ who: 'aw', text: 'web chat reply' } as { via?: string }), true);
});

test('nothing is read while the tab is hidden, and it carries on when shown', async () => {
  const tab = page(true);
  let reads = 0;
  const stop = startAlexaFeed({ fetchFeed: async () => { reads += 1; return { turns: [], latest: 0 }; }, onEntries: () => {}, page: tab, every: 5 });
  await wait(20);
  assert.equal(reads, 0);
  tab.show();
  await wait(20);
  stop();
  assert.ok(reads > 0);
});

test('a failing route or a feed that is off shows nothing and keeps polling', async () => {
  let reads = 0;
  const shown: FeedEntry[] = [];
  const stop = startAlexaFeed({
    fetchFeed: async () => { reads += 1; if (reads % 2) throw new Error('down'); return { error: 'The Alexa feed is off.' }; },
    onEntries: entries => shown.push(...entries), every: 5,
  });
  await wait(30);
  stop();
  assert.ok(reads > 2);
  assert.deepEqual(shown, []);
});

test('the bridge answer is read safely and each turn becomes a pair', () => {
  assert.equal(readFeed(null), null);
  assert.equal(readFeed({ error: 'off' }), null);
  assert.deepEqual(readFeed({ turns: [WALK, { id: 'x' }], latest: 4 }), { turns: [WALK], latest: 4 });
  assert.equal(feedTurns([WALK]).length, 2);
});

// The Alexa turn as the bridge's feed stores it: the same fields /chat returns.
const DRIVE: FeedEntry = {
  id: 5, said: 'can I plan to go for a drive', reply: 'Your letter says: Do not drive until your consultant has reviewed you.',
  source: { page: 2, section: 'Restrictions', text: 'Do not drive until your consultant has reviewed you.',
    highlight: 'Do not drive until your consultant has reviewed you.' },
  tool_trace: [{ tool: 'search_discharge_instructions', arguments: {}, ok: true }], help: null,
};
const CALF: FeedEntry = {
  id: 6, said: 'my calf is swollen', reply: "I'm sorry to hear that, Margaret. Your letter says: Call the ward.",
  source: { page: 2, section: 'Warning signs', text: 'Call the ward if you have: Pain, swelling in your calf.' },
  help: { actions: [{ urgency: 'contact_care_team', action: 'Call the ward on 0000 000 000 (fictional number)' }] },
  crisis: false,
};

test('an Alexa turn with a letter source opens the excerpt, as a web reply does, and is not spoken', () => {
  const alexa = replyView(feedReply(DRIVE), 'alexa');
  const web = replyView(readChat({ response: DRIVE.reply, source: DRIVE.source, tool_trace: DRIVE.tool_trace }));

  assert.equal(alexa.source?.section, 'Restrictions');
  assert.equal(alexa.source?.page, 2);
  assert.deepEqual(alexa.source, web.source);
  assert.deepEqual(alexa.chips, web.chips);
  assert.deepEqual(alexa.turn, { who: 'aw', text: DRIVE.reply, via: 'alexa' });
  assert.equal(alexa.speak, false);
  assert.equal(web.speak, true);
});

test('an Alexa help turn shows the Feeling unwell card and the warning signs, and is not spoken', () => {
  const view = replyView(feedReply(CALF), 'alexa');

  assert.deepEqual(view.help, [{ urgency: 'contact_care_team', action: 'Call the ward on 0000 000 000 (fictional number)' }]);
  assert.equal(view.source?.section, 'Warning signs');
  assert.equal(view.speak, false);
});

test('an Alexa greeting is AfterWard alone, via Alexa, and never added twice in a row', async () => {
  const { feedBubbles } = await import('../lib/alexa-feed.ts');
  const hello: FeedEntry = { id: 7, said: 'Open after ward', reply: 'Good morning, Margaret.  Your walk is next.', kind: 'launch' };

  // First time: only AfterWard's bubble, labelled via Alexa.
  assert.deepEqual(feedBubbles(hello, { who: 'you', text: 'what is next' }), { said: false, reply: true });
  assert.deepEqual(replyView(feedReply(hello), 'alexa').turn.via, 'alexa');
  // The same words already the latest Alexa message (she opened the skill again): not added.
  assert.deepEqual(feedBubbles(hello, { who: 'aw', text: 'Good morning, Margaret. Your walk is next.', via: 'alexa' }), { said: false, reply: false });
  // After the page's own greeting it is added: "AfterWard" and "AfterWard · via Alexa" are different.
  assert.deepEqual(feedBubbles(hello, { who: 'aw', text: 'Good morning, Margaret. Your walk is next.' }), { said: false, reply: true });
  // An ordinary turn is always a pair.
  assert.deepEqual(feedBubbles(WALK, { who: 'aw', text: WALK.reply }), { said: true, reply: true });
});

test('the same AfterWard message is never shown twice in a row from the same source', async () => {
  const { addTurn } = await import('../lib/alexa-feed.ts');
  type T = { who: 'you' | 'aw'; text: string; via?: 'alexa' };
  const hello: T = { who: 'aw', text: 'Good morning, Margaret. Your walk is next.' };

  // The web greeting twice (the greeting re-armed, or React dev mode running it twice): once.
  const once = addTurn<T>([], hello);
  assert.deepEqual(addTurn(once, { ...hello, text: 'Good morning, Margaret.  Your walk is next.' }), once);
  // The Alexa greeting after the web one: both, labelled differently.
  assert.equal(addTurn<T>(once, { ...hello, via: 'alexa' }).length, 2);
  // Her words are never dropped, and the same reply after she speaks again is shown again.
  const asked = addTurn<T>(addTurn<T>(once, { who: 'you', text: "what's next" }), { who: 'you', text: "what's next" });
  assert.equal(asked.length, 3);
  assert.equal(addTurn<T>(asked, hello).length, 4);
});
