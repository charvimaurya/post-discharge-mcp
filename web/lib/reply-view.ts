// What /demo shows for one AfterWard reply, the same for the web chat and for a reply said on
// the Echo: the letter excerpt (left panel), the "Feeling unwell?" card, the chips and the bubble.
// Only a web reply is spoken; a reply via Alexa was already spoken by the Echo.
import type { ChatReply, HelpAction, Source } from './assistant-data.ts';

export type ReplyView = {
  source: Source;
  // A symptom reply's help card; null leaves an open card where it is, shrunk to one line.
  help: HelpAction[] | null;
  chips: { kind: string; icon: string; text: string }[];
  turn: { who: 'aw'; text: string; via?: 'alexa' };
  speak: boolean;
};

export function replyView(reply: ChatReply, via?: 'alexa'): ReplyView {
  return {
    source: reply.source,
    help: reply.help,
    chips: reply.source
      ? [{ kind: '', icon: 'doc', text: `From your letter${reply.source.page ? `, page ${reply.source.page}` : ''}` }]
      : [],
    turn: { who: 'aw', text: reply.text || 'Sorry, I could not answer that.', ...(via ? { via } : {}) },
    speak: via !== 'alexa',
  };
}
