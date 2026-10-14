// Browser voice in and out. No AWS calls and no keys: the browser does the speech work.
// Speaking works in Chrome, Edge and Safari. Listening works in Chrome and Edge.

type Voice = Pick<SpeechSynthesisVoice, 'name' | 'lang' | 'localService' | 'default'>;

// An online voice that has not started talking by now is treated as not working.
export const VOICE_START_MS = 3000;

let current: SpeechSynthesisUtterance | null = null;
// Set once an online voice has failed in this tab, so later replies go straight to an installed one.
let onlineVoiceFailed = false;

export function resetVoiceChoice(): void {
  onlineVoiceFailed = false;
}

// A British voice first, as before. Edge often has no British voice installed, only Microsoft's
// online ("Natural") ones, which stream from the internet and can stay silent when that is blocked.
// So when an online voice fails, the fallback is a voice installed on the computer: British if
// there is one, otherwise the computer's default English voice.
export function chooseVoice(voices: Voice[], installedOnly: boolean): Voice | undefined {
  const english = voices.filter(v => v.lang?.toLowerCase().startsWith('en'));
  const british = english.filter(v => v.lang?.toLowerCase() === 'en-gb');
  if (!installedOnly) return british[0];
  const installed = english.filter(v => v.localService);
  return installed.find(v => v.lang?.toLowerCase() === 'en-gb') || installed.find(v => v.default) || installed[0];
}

export function speak(text: string): Promise<void> {
  return new Promise(resolve => {
    if (typeof window === 'undefined' || !('speechSynthesis' in window) || !text) return resolve();
    const synth = window.speechSynthesis;
    const interrupting = synth.speaking || synth.pending;
    if (interrupting) synth.cancel();

    function attempt(installedOnly: boolean) {
      const u = new SpeechSynthesisUtterance(text);
      u.lang = 'en-GB';
      u.rate = 0.95;
      const voice = chooseVoice(synth.getVoices(), installedOnly) as SpeechSynthesisVoice | undefined;
      if (voice) u.voice = voice;
      const online = !!voice && !voice.localService;
      let started = false;
      let settled = false;
      let watchdog: ReturnType<typeof setTimeout> | undefined;

      // Chrome can drop an utterance that nothing refers to before it finishes, so keep hold of it.
      current = u;
      const done = () => {
        if (settled) return;
        settled = true;
        clearTimeout(watchdog);
        if (current === u) current = null;
        resolve();
      };
      // The online voice did not work: say it again with an installed voice, once.
      const fallBack = () => {
        if (settled) return;
        settled = true;
        clearTimeout(watchdog);
        onlineVoiceFailed = true;
        synth.cancel();
        setTimeout(() => attempt(true), 120);
      };

      u.onstart = () => { started = true; clearTimeout(watchdog); };
      u.onend = done;
      u.onerror = e => {
        // Stopped on purpose (she spoke, or a new reply came): nothing to retry.
        if (e.error === 'interrupted' || e.error === 'canceled' || !online || started) done();
        else fallBack();
      };
      if (online) watchdog = setTimeout(() => { if (!started) fallBack(); }, VOICE_START_MS);

      // Chrome can be left paused by an earlier tab or utterance; resume() is harmless otherwise.
      synth.resume();
      synth.speak(u);
    }

    // Chrome silently drops speak() called straight after cancel(), so give it a moment.
    const begin = () => attempt(onlineVoiceFailed);
    if (interrupting) setTimeout(begin, 120); else begin();
  });
}

// One recognition result: its best transcript, and whether the browser has settled on it.
type RecognitionResult = { isFinal: boolean; 0: { transcript: string } };
type Recognition = {
  lang: string; continuous: boolean; interimResults: boolean; maxAlternatives: number;
  onresult: ((e: { results: ArrayLike<RecognitionResult> }) => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void; stop: () => void;
};

// The browser's own one-phrase mode ends at the first short pause, so "Can you order the... "
// was sent before she had finished. Instead, listening runs on until she has been quiet a while.
// Someone recovering from an operation may well pause mid-sentence.
// While the browser is still unsure of her last words, wait this long for more.
export const PAUSE_ENDS_TURN_MS = 2000;
// Once the browser has settled her last words (it does so after its own short pause), she has
// already been quiet for a moment, so a shorter wait is enough. This keeps the answer quick.
export const SETTLED_PAUSE_MS = 1000;
// Waiting for her first word, before giving up with nothing heard.
export const WAIT_FOR_SPEECH_MS = 8000;
// A single turn never runs longer than this.
export const LONGEST_TURN_MS = 30000;

export function canListen(): boolean {
  if (typeof window === 'undefined') return false;
  const w = window as unknown as Record<string, unknown>;
  return !!(w.SpeechRecognition || w.webkitSpeechRecognition);
}

let finishCurrent: (() => void) | null = null;

// Tapping the microphone again: she has finished, send what was heard now.
export function finishListening(): void {
  finishCurrent?.();
}

// Listens until she pauses for PAUSE_ENDS_TURN_MS, then returns what was heard ('' if nothing).
// onHeard gets the words so far, as they come, so the screen can show them.
export function listenOnce(onHeard?: (soFar: string) => void): Promise<string> {
  return new Promise((resolve, reject) => {
    const w = window as unknown as Record<string, new () => Recognition>;
    const Ctor = w.SpeechRecognition || w.webkitSpeechRecognition;
    if (!Ctor) return reject(new Error('This browser cannot listen. Use Chrome or Edge, or type instead.'));
    const rec = new Ctor();
    rec.lang = 'en-GB';
    rec.continuous = true;
    rec.interimResults = true;
    rec.maxAlternatives = 1;

    let heard = '';
    let failed: Error | null = null;
    let quiet: ReturnType<typeof setTimeout> | undefined;
    const longest = setTimeout(() => finish(), LONGEST_TURN_MS);

    function finish() {
      clearTimeout(quiet);
      clearTimeout(longest);
      try { rec.stop(); } catch { /* already stopped */ }
    }
    function waitForQuiet(ms: number) {
      clearTimeout(quiet);
      quiet = setTimeout(finish, ms);
    }

    finishCurrent = finish;
    rec.onresult = e => {
      // Every result so far, settled or not, in order: the whole of what she has said.
      heard = Array.from(e.results, r => r[0]?.transcript || '').join(' ').replace(/\s+/g, ' ').trim();
      onHeard?.(heard);
      const last = e.results[e.results.length - 1];
      waitForQuiet(last?.isFinal ? SETTLED_PAUSE_MS : PAUSE_ENDS_TURN_MS);
    };
    rec.onerror = e => {
      // Silence, or our own stop: not a failure, just nothing more to hear.
      if (e.error === 'no-speech' || e.error === 'aborted') return;
      failed = new Error(e.error === 'not-allowed' ? 'Microphone permission was refused.' : `Microphone error: ${e.error}`);
    };
    rec.onend = () => {
      clearTimeout(quiet);
      clearTimeout(longest);
      if (finishCurrent === finish) finishCurrent = null;
      if (failed && !heard) reject(failed);
      else resolve(heard);
    };
    rec.start();
    waitForQuiet(WAIT_FOR_SPEECH_MS);
  });
}
