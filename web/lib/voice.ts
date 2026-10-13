// Browser voice in and out. No AWS calls and no keys: the browser does the speech work.
// Speaking works in Chrome, Edge and Safari. Listening works in Chrome and Edge.

let current: SpeechSynthesisUtterance | null = null;

export function speak(text: string): Promise<void> {
  return new Promise(resolve => {
    if (typeof window === 'undefined' || !('speechSynthesis' in window) || !text) return resolve();
    const synth = window.speechSynthesis;
    const interrupting = synth.speaking || synth.pending;
    if (interrupting) synth.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = 'en-GB';
    u.rate = 0.95;
    const voice = synth.getVoices().find(v => v.lang === 'en-GB');
    if (voice) u.voice = voice;
    // Chrome can drop an utterance that nothing refers to before it finishes, so keep hold of it.
    current = u;
    const done = () => { if (current === u) current = null; resolve(); };
    u.onend = done;
    u.onerror = done;
    const start = () => {
      // Chrome can be left paused by an earlier tab or utterance; resume() is harmless otherwise.
      synth.resume();
      synth.speak(u);
    };
    // Chrome silently drops speak() called straight after cancel(), so give it a moment.
    if (interrupting) setTimeout(start, 120); else start();
  });
}

type Recognition = {
  lang: string; interimResults: boolean; maxAlternatives: number;
  onresult: ((e: { results: { 0: { transcript: string } }[] }) => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void; stop: () => void;
};

export function canListen(): boolean {
  if (typeof window === 'undefined') return false;
  const w = window as unknown as Record<string, unknown>;
  return !!(w.SpeechRecognition || w.webkitSpeechRecognition);
}

// Listens for one sentence and returns what was heard ('' if nothing was heard).
export function listenOnce(): Promise<string> {
  return new Promise((resolve, reject) => {
    const w = window as unknown as Record<string, new () => Recognition>;
    const Ctor = w.SpeechRecognition || w.webkitSpeechRecognition;
    if (!Ctor) return reject(new Error('This browser cannot listen. Use Chrome or Edge, or type instead.'));
    const rec = new Ctor();
    rec.lang = 'en-GB';
    rec.interimResults = false;
    rec.maxAlternatives = 1;
    let heard = '';
    rec.onresult = e => { heard = e.results[0]?.[0]?.transcript || ''; };
    rec.onerror = e => reject(new Error(e.error === 'not-allowed' ? 'Microphone permission was refused.' : `Microphone error: ${e.error}`));
    rec.onend = () => resolve(heard.trim());
    rec.start();
  });
}
