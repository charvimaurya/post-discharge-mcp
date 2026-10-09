// The one speech implementation: the browser's built-in text-to-speech.

function available(): boolean {
  return typeof window !== 'undefined' && 'speechSynthesis' in window;
}

// Call from the Start click: browsers only allow speech after a user gesture.
export function unlockSpeech(): void {
  if (available()) window.speechSynthesis.speak(new SpeechSynthesisUtterance(''));
}

export function speak(text: string): void {
  if (!available() || !text) return;
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = 'en-GB';
  window.speechSynthesis.speak(utterance);
}
