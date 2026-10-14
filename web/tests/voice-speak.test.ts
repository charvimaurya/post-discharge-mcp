// AfterWard's voice: a British voice first, and a voice installed on the computer when an online
// voice stays silent (as Edge's "Online (Natural)" voices can). No browser needed: speech is faked.
import { test, mock } from 'node:test';
import assert from 'node:assert/strict';
import { chooseVoice, resetVoiceChoice, speak, VOICE_START_MS } from '../lib/voice.ts';

const SONIA = { name: 'Microsoft Sonia Online (Natural) - English (United Kingdom)', lang: 'en-GB', localService: false, default: false };
const DAVID = { name: 'Microsoft David - English (United States)', lang: 'en-US', localService: true, default: true };
const ZIRA = { name: 'Microsoft Zira - English (United States)', lang: 'en-US', localService: true, default: false };
const HAZEL = { name: 'Microsoft Hazel - English (United Kingdom)', lang: 'en-GB', localService: true, default: false };
const EDGE_HERE = [DAVID, ZIRA, SONIA];

test('a British voice is chosen first, as before', () => {
  assert.equal(chooseVoice(EDGE_HERE, false), SONIA);
});

test('the fallback is an installed voice: British if there is one, else the default English one', () => {
  assert.equal(chooseVoice(EDGE_HERE, true), DAVID);
  assert.equal(chooseVoice([...EDGE_HERE, HAZEL], true), HAZEL);
  assert.equal(chooseVoice([SONIA], true), undefined);
});

type Spoken = { text: string; voice?: typeof SONIA; onstart?: () => void; onend?: () => void; onerror?: (e: { error: string }) => void };

// A fake browser: `behave` decides what each spoken utterance does.
function fakeBrowser(voices: typeof EDGE_HERE, behave: (u: Spoken) => void) {
  const spoken: Spoken[] = [];
  const synth = {
    speaking: false, pending: false,
    getVoices: () => voices,
    cancel() {}, resume() {},
    speak(u: Spoken) { spoken.push(u); behave(u); },
  };
  (globalThis as Record<string, unknown>).window = { speechSynthesis: synth };
  (globalThis as Record<string, unknown>).SpeechSynthesisUtterance = class { text: string; constructor(t: string) { this.text = t; } };
  resetVoiceChoice();
  return spoken;
}

test('an online voice that never starts is replaced by an installed voice, and later replies skip it', async () => {
  mock.timers.enable({ apis: ['setTimeout'] });
  try {
    const spoken = fakeBrowser(EDGE_HERE, u => {
      if (u.voice?.localService) { u.onstart?.(); u.onend?.(); }   // installed voice works; the online one stays silent
    });

    const first = speak('Good morning, Margaret.');
    assert.equal(spoken.length, 1);
    assert.equal(spoken[0].voice, SONIA);
    mock.timers.tick(VOICE_START_MS);   // nothing heard from the online voice
    mock.timers.tick(200);              // the short wait after cancel()
    await first;

    assert.equal(spoken.length, 2);
    assert.equal(spoken[1].voice, DAVID);
    assert.equal(spoken[1].text, 'Good morning, Margaret.');

    await speak('Next is your walk.');
    assert.equal(spoken[2].voice, DAVID);   // no second wait on the silent voice
  } finally { mock.timers.reset(); }
});

test('an online voice that fails before speaking is replaced at once', async () => {
  mock.timers.enable({ apis: ['setTimeout'] });
  try {
    const spoken = fakeBrowser(EDGE_HERE, u => {
      if (u.voice?.localService) { u.onstart?.(); u.onend?.(); } else u.onerror?.({ error: 'synthesis-failed' });
    });
    const done = speak('Hello');
    mock.timers.tick(200);
    await done;
    assert.deepEqual(spoken.map(u => u.voice), [SONIA, DAVID]);
  } finally { mock.timers.reset(); }
});

test('a working online voice is kept', async () => {
  const spoken = fakeBrowser(EDGE_HERE, u => { u.onstart?.(); u.onend?.(); });
  await speak('Hello');
  await speak('Again');
  assert.deepEqual(spoken.map(u => u.voice), [SONIA, SONIA]);
});

test('speech stopped on purpose is not repeated', async () => {
  const spoken = fakeBrowser(EDGE_HERE, u => u.onerror?.({ error: 'interrupted' }));
  await speak('Hello');
  assert.equal(spoken.length, 1);
});

test('an installed voice that fails ends quietly, without trying again', async () => {
  const spoken = fakeBrowser([DAVID], u => u.onerror?.({ error: 'synthesis-failed' }));
  await speak('Hello');
  assert.equal(spoken.length, 1);
});
