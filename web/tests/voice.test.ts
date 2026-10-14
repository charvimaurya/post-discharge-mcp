// Listening waits for a real pause, so a sentence with a pause in it is not cut short.
// No browser needed: a fake recognition object stands in for the microphone.
import { test, mock } from 'node:test';
import assert from 'node:assert/strict';
import { finishListening, listenOnce, LONGEST_TURN_MS, PAUSE_ENDS_TURN_MS, SETTLED_PAUSE_MS, WAIT_FOR_SPEECH_MS } from '../lib/voice.ts';

type Result = { isFinal: boolean; 0: { transcript: string } };

class FakeRecognition {
  static last: FakeRecognition;
  lang = ''; continuous = false; interimResults = false; maxAlternatives = 1;
  onresult: ((e: { results: Result[] }) => void) | null = null;
  onerror: ((e: { error: string }) => void) | null = null;
  onend: (() => void) | null = null;
  results: Result[] = [];
  stopped = false;
  constructor() { FakeRecognition.last = this; }
  start() {}
  stop() { if (!this.stopped) { this.stopped = true; this.onend?.(); } }
  say(text: string, isFinal = true) {
    this.results.push({ isFinal, 0: { transcript: text } });
    this.onresult?.({ results: this.results });
  }
}

function setUp() {
  (globalThis as unknown as { window: unknown }).window = { SpeechRecognition: FakeRecognition };
  mock.timers.enable({ apis: ['setTimeout'] });
}
function tearDown() {
  mock.timers.reset();
}

test('a short pause mid-sentence does not end her turn', async () => {
  setUp();
  try {
    const heard = listenOnce();
    const mic = FakeRecognition.last;
    assert.equal(mic.continuous, true);

    mic.say('can you order the', false);          // the browser is not yet sure she has finished
    mock.timers.tick(PAUSE_ENDS_TURN_MS - 500);   // she pauses, but not for long
    assert.equal(mic.stopped, false);
    mic.results.pop();
    mic.say('can you order the blood thinner for me');
    mock.timers.tick(SETTLED_PAUSE_MS);           // settled, and quiet: she has finished

    assert.equal(await heard, 'can you order the blood thinner for me');
  } finally { tearDown(); }
});

test('the words so far are reported as she speaks', async () => {
  setUp();
  try {
    const seen: string[] = [];
    const heard = listenOnce(text => seen.push(text));
    const mic = FakeRecognition.last;

    mic.say('can you', false);
    mic.results.pop();
    mic.say('can you order', true);
    mock.timers.tick(PAUSE_ENDS_TURN_MS);

    assert.deepEqual(seen, ['can you', 'can you order']);
    assert.equal(await heard, 'can you order');
  } finally { tearDown(); }
});

test('tapping the microphone again sends what was heard straight away', async () => {
  setUp();
  try {
    const heard = listenOnce();
    FakeRecognition.last.say('what is next');
    finishListening();
    assert.equal(await heard, 'what is next');
  } finally { tearDown(); }
});

test('silence before any word ends with nothing heard, not an error', async () => {
  setUp();
  try {
    const heard = listenOnce();
    FakeRecognition.last.onerror?.({ error: 'no-speech' });
    mock.timers.tick(WAIT_FOR_SPEECH_MS);
    assert.equal(await heard, '');
  } finally { tearDown(); }
});

test('a very long turn is still ended', async () => {
  setUp();
  try {
    const heard = listenOnce();
    const mic = FakeRecognition.last;
    for (let t = 0; t < LONGEST_TURN_MS; t += PAUSE_ENDS_TURN_MS / 2) {
      mic.say('and');
      mock.timers.tick(PAUSE_ENDS_TURN_MS / 2);
    }
    await heard;
    assert.equal(mic.stopped, true);
  } finally { tearDown(); }
});

test('a refused microphone is reported', async () => {
  setUp();
  try {
    const heard = listenOnce();
    const mic = FakeRecognition.last;
    mic.onerror?.({ error: 'not-allowed' });
    mic.stop();
    await assert.rejects(heard, /permission was refused/);
  } finally { tearDown(); }
});

test('once her words are settled, a short quiet is enough to send them', async () => {
  setUp();
  try {
    const heard = listenOnce();
    const mic = FakeRecognition.last;
    mic.say('what is next');                       // settled by the browser
    mock.timers.tick(SETTLED_PAUSE_MS - 100);
    assert.equal(mic.stopped, false);
    mock.timers.tick(100);
    assert.equal(await heard, 'what is next');
  } finally { tearDown(); }
});

test('words the browser is still unsure of get the longer wait', async () => {
  setUp();
  try {
    const heard = listenOnce();
    const mic = FakeRecognition.last;
    mic.say('can you', false);
    mock.timers.tick(SETTLED_PAUSE_MS + 100);
    assert.equal(mic.stopped, false);
    mock.timers.tick(PAUSE_ENDS_TURN_MS);
    assert.equal(await heard, 'can you');
  } finally { tearDown(); }
});
