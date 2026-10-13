"""
Pick the discharge-letter evidence that an agent reply actually used.

search_discharge_instructions returns several chunks ranked by
vector distance to the QUERY. The nearest chunk is often not the
one the answer quotes (a short query like "driving" can sit closer
to a long header chunk). So the source is chosen AFTER the reply is
written, by matching the reply against the letter's own items.

The source always comes from search_discharge_instructions results,
never from the model or from get_recovery_plan.
"""

import math
import re
from typing import Any


# Without a shared letter phrase, a reply supports an item only
# if it shares this many words with it, at least one of them
# found in no other returned item.
MIN_REPLY_SHARED_WORDS = 2

# Common words that would make unrelated items look similar.
# "not" is kept on purpose: "do not drive" must stay distinct.
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "has", "have", "if", "in", "is", "it", "its", "of", "on", "or",
    "so", "that", "the", "this", "to", "was", "with", "you", "your",
}

# Date and time words. Dates come from get_recovery_plan, not
# letter wording, so they never count as a phrase's content.
_DATE_WORDS = {
    "january", "february", "march", "april", "may", "june", "july",
    "august", "september", "october", "november", "december",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept",
    "oct", "nov", "dec", "monday", "tuesday", "wednesday",
    "thursday", "friday", "saturday", "sunday", "am", "pm",
}

# Bullet glyphs that PDF extraction leaves behind (\x7f, •, ▪).
_BULLET = re.compile(r"[\x7f•▪]")

# A numbered list marker on its own line, e.g. "\n3.\n".
_NUMBERED_ITEM = re.compile(r"\n\s*\d+\.\s*\n")

# Evidence tag the model appends to paperwork answers, e.g.
#   [[evidence: doc_p1_c1 | Continue as directed.]]
# It is stripped before the reply is spoken or stored.
_CITATION = re.compile(
    r"\[\[\s*evidence\s*:\s*([^\]|]+?)\s*(?:\|\s*(.*?)\s*)?\]\]",
    flags=re.IGNORECASE | re.DOTALL,
)


def split_citation(
    response_text: str,
) -> tuple[str, str | None, str | None]:
    """
    Remove evidence tags from a reply.

    Returns (spoken_text, cited_chunk_id, cited_line). The last
    tag wins. The cited values are only claims; they are checked
    against the real search results in select_rag_source().
    """

    tags = _CITATION.findall(response_text or "")
    spoken = _CITATION.sub("", response_text or "")
    spoken = re.sub(r"[ \t]+", " ", spoken).strip()

    if not tags:
        return spoken, None, None

    chunk_id, line = tags[-1]

    return spoken, chunk_id.strip() or None, (line or "").strip() or None


def collect_rag_matches(
    tool_name: str,
    structured_result: Any,
) -> list[dict]:
    """Return the match list from a successful RAG tool result."""

    if tool_name != "search_discharge_instructions":
        return []

    if not isinstance(structured_result, dict):
        return []

    if not structured_result.get("ok"):
        return []

    data = structured_result.get("data")

    if not isinstance(data, list):
        return []

    return [
        match
        for match in data
        if isinstance(match, dict) and match.get("text")
    ]


def _words(text: str) -> set[str]:
    return {
        word
        for word in re.findall(r"[a-z0-9]+", text.lower())
        if word not in _STOPWORDS
    }


def _normalise(text: str) -> str:
    """Lowercase words only, so quotes match across punctuation."""

    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def _is_heading(line: str) -> bool:
    """Section headings such as "RESTRICTIONS" are all caps."""

    letters = [c for c in line if c.isalpha()]
    return len(letters) >= 3 and all(c.isupper() for c in letters)


def split_letter_items(text: str) -> list[str]:
    """
    Split a chunk into the letter's own items: one bullet point,
    one numbered medicine, or one plain paragraph each. Wrapped
    lines are re-joined; section headings are separators.
    """

    text = _BULLET.sub("\n\n", text)
    text = _NUMBERED_ITEM.sub("\n\n", text)

    items = []
    current: list[str] = []

    def flush():
        if current:
            items.append(" ".join(current))
            current.clear()

    for raw_line in text.split("\n"):
        line = raw_line.strip()

        if not line or _is_heading(line):
            flush()
            continue

        current.append(line)

    flush()

    return items


def select_rag_source(
    response_text: str,
    rag_matches: list[dict],
    context_texts: list[str] | tuple[str, ...] = (),
    cited_chunk_id: str | None = None,
    cited_line: str | None = None,
    entity_names: list[str] | tuple[str, ...] = (),
) -> dict | None:
    """
    Return the source for the letter item that supports the reply,
    or None when no returned item can be shown to support it.

    Every candidate, including one the model cites, must pass the
    same support check (_EvidenceScorer.supports):

    - The requirement comes from the EARLIEST reply sentence that
      uses the letter, because paperwork replies state the
      letter's wording first and any plan fact (e.g. an
      appointment date) second.
    - If that sentence repeats a letter phrase (2+ words, 2+
      content words, dates excluded), the item must contain its
      strongest such phrase.
    - Otherwise the item must share at least 2 of that
      sentence's words, one of them found in no other returned
      item (a paraphrase).
    - If the reply or question names an entity from the grounded
      tool results (e.g. a medication) that a returned item
      contains, the item must contain it too.

    1. A cited chunk + line is used only if it passes the check.
    2. Otherwise the best supporting item across ALL returned
       results is used; ties keep the closer-ranked match.
    3. If nothing passes, the source is None.

    context_texts (the patient's question and search queries)
    help ranking and entity detection, but can never on their
    own make an item "supporting".
    """

    candidates = _unique_items(rag_matches)

    if not candidates:
        return None

    scorer = _EvidenceScorer(
        response_text,
        candidates,
        context_texts,
        entity_names,
    )

    # 1. The model's citation, if it really supports the reply.
    cited = _cited_item(rag_matches, cited_chunk_id, cited_line)

    # What the excerpt should answer: the reply first, then the question.
    answer_text = " ".join([response_text or "", *context_texts])

    if cited is not None and scorer.supports(cited[1]):
        return _source(*cited, answer_text)

    # 2. Best supporting item across every returned result.
    best = None
    best_rank = None

    for match, item in candidates:

        if not scorer.supports(item):
            continue

        rank = scorer.rank(item)

        if best_rank is None or rank > best_rank:
            best, best_rank = (match, item), rank

    if best is None:
        return None

    return _source(*best, answer_text)


def _cited_item(
    rag_matches: list[dict],
    cited_chunk_id: str | None,
    cited_line: str | None,
) -> tuple[dict, str] | None:
    """
    The (match, item) the model's tag points to, if it exists.

    Only a chunk the search really returned, and an item really in
    that chunk containing the cited line, qualify. Whether it
    SUPPORTS the reply is checked separately.
    """

    if not cited_chunk_id or not cited_line:
        return None

    line = _normalise(cited_line)

    if not line:
        return None

    for match in rag_matches:

        if match.get("chunk_id") != cited_chunk_id:
            continue

        for item in split_letter_items(match["text"]):
            if _contains_phrase(_normalise(item), line):
                return match, item

    return None


def _contains_phrase(normalised_text: str, phrase: str) -> bool:
    """Whole-word phrase match on normalised text."""

    return f" {phrase} " in f" {normalised_text} "


class _EvidenceScorer:
    """Decides which returned letter items support a reply."""

    def __init__(self, response_text, candidates, context_texts, entity_names):

        self.items = [_normalise(item) for _, item in candidates]
        self.item_words = [_words(item) for _, item in candidates]

        # How many returned items each word appears in.
        self.frequency: dict[str, int] = {}
        for words in self.item_words:
            for word in words:
                self.frequency[word] = self.frequency.get(word, 0) + 1

        self.size = len(candidates)

        self.reply_words = _words(response_text)
        self.context_words = set()
        for text in context_texts:
            self.context_words |= _words(text)

        self.phrase, self.sentence_words = self._requirement(response_text)
        self.entities = self._mentioned_entities(
            response_text, context_texts, entity_names,
        )

    def weight(self, word: str) -> float:
        # Rare words ("drive", a drug name) outweigh common ones
        # ("take", "day"). Words in no item get the top weight.
        count = self.frequency.get(word, 0)
        return math.log((self.size + 1) / (count + 1)) + 1

    def _requirement(self, response_text: str):
        """
        (phrase, None) or (None, sentence_words) for the earliest
        sentence that uses the letter; (None, None) if none does.
        """

        for sentence in re.split(r"(?<=[.!?;])\s+", response_text or ""):

            phrase = self._strongest_phrase(_normalise(sentence))

            if phrase is not None:
                return phrase, None

            words = _words(sentence)

            if any(self._paraphrases(item_words, words) for item_words in self.item_words):
                return None, words

        return None, None

    def _paraphrases(self, item_words: set[str], words: set[str]) -> bool:
        shared = item_words & words
        return (
            len(shared) >= MIN_REPLY_SHARED_WORDS
            and any(self.frequency.get(word) == 1 for word in shared)
        )

    def _strongest_phrase(self, reply: str) -> str | None:
        """
        The rarest-weighted phrase the text shares with any item.

        Phrases are maximal runs of 2+ words found verbatim (after
        normalisation) in some item, with 2+ content words, so
        "as directed", "it is safe" or a bare date do not count.
        """

        tokens = reply.split()
        best, best_weight = None, 0.0

        for start in range(len(tokens)):

            end = start + 2
            longest = None

            while end <= len(tokens):
                phrase = " ".join(tokens[start:end])
                if not any(_contains_phrase(item, phrase) for item in self.items):
                    break
                longest = phrase
                end += 1

            if longest is None:
                continue

            content = [
                w
                for w in longest.split()
                if w not in _STOPWORDS
                and w not in _DATE_WORDS
                and not w.isdigit()
            ]

            if len(content) < 2:
                continue

            phrase_weight = sum(self.weight(w) for w in content)

            if phrase_weight > best_weight:
                best, best_weight = longest, phrase_weight

        return best

    def _mentioned_entities(self, response_text, context_texts, entity_names):
        """Grounded entity names the reply or question mentions."""

        spoken = " ".join([_normalise(response_text)] + [_normalise(t) for t in context_texts])

        mentioned = []

        for name in entity_names:
            normalised = _normalise(name or "")
            if not normalised or not _contains_phrase(spoken, normalised):
                continue
            # Only binding if some returned item names it.
            if any(_contains_phrase(item, normalised) for item in self.items):
                mentioned.append(normalised)

        return mentioned

    def supports(self, item: str) -> bool:

        normalised = _normalise(item)
        words = _words(item)

        for entity in self.entities:
            if not _contains_phrase(normalised, entity):
                return False

        if self.phrase is not None:
            return _contains_phrase(normalised, self.phrase)

        if self.sentence_words is not None:
            return self._paraphrases(words, self.sentence_words)

        # No sentence of the reply uses the letter.
        return False

    def rank(self, item: str) -> tuple[float, float]:
        """Rarity-weighted coverage by reply + question words."""

        words = _words(item)
        evidence = self.reply_words | self.context_words
        shared_weight = sum(self.weight(w) for w in words & evidence)
        total = sum(self.weight(w) for w in words) or 1.0

        return shared_weight / total, shared_weight


def _unique_items(rag_matches: list[dict]) -> list[tuple[dict, str]]:
    """
    Split matches into items, dropping repeats.

    Neighbouring chunks overlap, so the same item (or a cut-off
    piece of it) can appear twice; keeping both would make its
    words look common. The first, closer-ranked copy is kept.
    """

    items = [
        (match, item, _normalise(item))
        for match in rag_matches
        for item in split_letter_items(match["text"])
    ]

    unique = []

    for index, (match, item, normalised) in enumerate(items):

        if not normalised:
            continue

        duplicate = any(
            normalised in other
            and (normalised != other or other_index < index)
            for other_index, (_, _, other) in enumerate(items)
            if other_index != index
        )

        if not duplicate:
            unique.append((match, item))

    return unique


def _source(match: dict, item: str, answer_text: str = "") -> dict:
    """
    Build the API source from one RAG match and its item.

    section, text and highlight are the clean excerpt for the letter
    panel (clean_passage). passage and highlighted_line are kept for
    older readers: the raw chunk and the matched item.
    """

    excerpt = clean_passage(match.get("text") or "", answer_text, item) or {}

    return {
        "document_id": match.get("document_id"),
        "page": match.get("page"),
        "chunk_id": match.get("chunk_id"),
        "section": excerpt.get("section"),
        "text": excerpt.get("text") or item,
        "highlight": excerpt.get("highlight") or item,
        "passage": match.get("text"),
        "highlighted_line": item,
    }


# ---------- A clean, readable excerpt for the letter panel ----------

# Most sentences an excerpt keeps.
MAX_EXCERPT_SENTENCES = 3

_NUMBER_ONLY = re.compile(r"^\s*(\d+)\.\s*$")
_NUMBER_LEAD = re.compile(r"^\s*(\d+)\.\s+(\S.*)$")
_BULLET_LEAD = re.compile(r"^\s*(?:[\x7f•▪●◦‣∙·*]|-\s)\s*")
_SENTENCE_END = re.compile(r"[.!?:]\s*$")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(\"'])")

# Everyday words patients use for a medicine, so "blood thinner"
# can find the Apixaban item. Matching only; the letter's words
# are never replaced.
_EVERYDAY_TERMS = {
    "blood thinner": (
        "apixaban", "rivaroxaban", "edoxaban", "dabigatran",
        "warfarin", "enoxaparin", "dalteparin", "heparin",
    ),
}


def _blocks(chunk_text: str) -> list[dict]:
    """
    Rebuild the letter's own blocks from a chunk.

    PDF line wraps are re-joined (a line that does not end in
    . ! ? : continues on the next). A numbered item, a bullet or an
    ALL-CAPS heading always starts a new block. Each block keeps the
    nearest heading above it as its section.
    """

    blocks: list[dict] = []
    section: str | None = None
    current: dict | None = None
    pending_number: str | None = None

    def close():
        nonlocal current
        if current and current["text"].strip():
            blocks.append(current)
        current = None

    def start(kind: str, text: str, number: str | None = None):
        nonlocal current
        close()
        current = {"kind": kind, "number": number, "text": text.strip(), "section": section}

    for raw in (chunk_text or "").split("\n"):
        line = raw.strip()

        if not line:
            # A blank line ends a paragraph, but not a numbered item
            # whose text has not started yet.
            if pending_number is None:
                close()
            continue

        number_only = _NUMBER_ONLY.match(line)
        if number_only:
            close()
            pending_number = number_only.group(1)
            continue

        if _is_heading(line) and pending_number is None:
            close()
            section = line.strip()
            continue

        if pending_number is not None:
            start("item", line, pending_number)
            pending_number = None
            continue

        number_lead = _NUMBER_LEAD.match(line)
        if number_lead:
            start("item", number_lead.group(2), number_lead.group(1))
            continue

        if _BULLET_LEAD.match(line):
            start("bullet", _BULLET_LEAD.sub("", line, count=1))
            continue

        if current is None:
            start("para", line)
        elif current["kind"] == "para" and _SENTENCE_END.search(current["text"]):
            # A finished sentence followed by a new line: a new paragraph.
            start("para", line)
        else:
            # A wrapped line, or the text after a bullet glyph on its own line.
            current["text"] = f"{current['text']} {line}".strip()

    close()
    return blocks


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split(text.strip()) if s.strip()]


def _trim_partial_edges(blocks: list[dict]) -> list[dict]:
    """Drop the cut-off sentence at the start and end of the chunk."""

    if blocks:
        first = blocks[0]
        # A chunk that starts mid-sentence ("akfast. 2.") begins lower case.
        if first["kind"] == "para" and first["text"][:1].islower():
            sentences = _sentences(first["text"])
            rest = " ".join(sentences[1:]) if len(sentences) > 1 else ""
            if rest:
                first["text"] = rest
            else:
                blocks = blocks[1:]

    if blocks:
        last = blocks[-1]
        if not _SENTENCE_END.search(last["text"]):
            sentences = _sentences(last["text"])
            complete = [s for s in sentences if _SENTENCE_END.search(s)]
            if complete:
                last["text"] = " ".join(complete)
            else:
                blocks = blocks[:-1]

    return blocks


def _expanded_words(text: str) -> set[str]:
    """Words of `text`, plus medicine names for an everyday term it uses."""

    words = _words(text)
    lowered = (text or "").lower()

    for term, names in _EVERYDAY_TERMS.items():
        if term in lowered:
            words |= set(names)

    return words


# Most rows of a list shown in one excerpt.
MAX_LIST_ROWS = 8

# Most words in a table's column headings ("Medicine  How to take it  Status") or in
# one short cell after a row's last sentence ("New").
_MAX_HEADING_WORDS = 8
_MAX_CELL_WORDS = 2
_AFTER_LAST_SENTENCE = re.compile(r"^(.*[.!?])\s+([^.!?]+)$", re.DOTALL)


def _without_table_cells(blocks: list[dict]) -> list[dict]:
    """
    Remove what a table leaves behind when a PDF is read as plain text.

    A medicines table arrives as its column headings on one line, then
    numbered rows that each end with a short status cell ("New"). Neither
    is a sentence of the letter, and shown raw they read as nonsense
    ("Medicine How to take it Status"). The headings line is dropped, and
    so is the short cell after each row's last sentence. A chunk without
    such a headings line is returned unchanged.
    """

    cleaned: list[dict] = []
    cells: list[str] = []
    in_table = False

    for index, block in enumerate(blocks):
        following = blocks[index + 1] if index + 1 < len(blocks) else None

        if (
            block["kind"] == "para"
            and following is not None
            and following["kind"] == "item"
            and not re.search(r"[.!?:]", block["text"])
            and len(block["text"].split()) <= _MAX_HEADING_WORDS
        ):
            in_table = True
            continue

        if block["kind"] != "item":
            in_table = False
        elif in_table:
            cell = _AFTER_LAST_SENTENCE.match(block["text"])

            if cell and len(cell.group(2).split()) <= _MAX_CELL_WORDS:
                cells.append(cell.group(2).strip())
                block = dict(block, text=cell.group(1).strip(), table_row=True)
            else:
                block = dict(block, table_row=True)

        cleaned.append(block)

    # The last row of a table also swallows the paragraph printed after the table
    # ("... if constipated. New Usual medicines before admission: none."). Its status
    # cell is the one the other rows ended with, so the row is cut there too.
    for cell_text in set(cells):
        ends_row = re.compile(rf"([.!?])\s+{re.escape(cell_text)}\s+\S")

        for index, block in enumerate(cleaned):
            found = ends_row.search(block["text"]) if block.get("table_row") else None

            if found:
                cleaned[index] = dict(block, text=block["text"][:found.end(1)].strip())

    return cleaned


def _block_text(block: dict) -> str:
    if block["kind"] == "item":
        return f"{block['number']}. {block['text']}"
    if block["kind"] == "bullet":
        return f"- {block['text']}"
    return block["text"]


def clean_passage(
    chunk_text: str,
    query_or_answer: str,
    item: str | None = None,
) -> dict | None:
    """
    A short, readable excerpt of the letter for the panel.

    Returns {"section", "text", "highlight"}:
      text       the one block that answers (a numbered item, a bullet
                 or a paragraph), at most about three sentences, with
                 PDF line wraps re-joined and bullets as "- ".
      highlight  the one sentence in `text` that answers.
      section    the nearest ALL-CAPS heading above it, title-cased,
                 or None if the chunk has none above it.

    `item` is the letter item the evidence check chose; when given,
    the block containing it wins. Otherwise the block sharing the most
    rare words with `query_or_answer` wins. Only whitespace, bullet
    glyphs and trimming change; the letter's words never do.
    """

    blocks = _without_table_cells(_trim_partial_edges(_blocks(chunk_text)))

    if not blocks:
        return None

    target_words = _expanded_words(query_or_answer)

    # How many blocks each word is in, so rare words count most.
    frequency: dict[str, int] = {}
    for block in blocks:
        for word in _words(block["text"]):
            frequency[word] = frequency.get(word, 0) + 1

    def weight(word: str) -> float:
        return math.log((len(blocks) + 1) / (frequency.get(word, 0) + 1)) + 1

    def score(text: str) -> float:
        return sum(weight(w) for w in _words(text) & target_words)

    chosen = None

    if item:
        wanted = _normalise(item)

        # A medicines table reaches here as one long item holding every row. Show the
        # rows as the letter's list and mark the one row the answer is about.
        rows = [
            block for block in blocks
            if block["kind"] == "item" and _normalise(block["text"]) and _normalise(block["text"]) in wanted
        ][:MAX_LIST_ROWS]

        if len(rows) >= 2:
            row = max(rows, key=lambda block: score(block["text"]))
            section = row.get("section")

            return {
                "section": section.title() if section else None,
                "text": "\n".join(_block_text(block) for block in rows),
                "highlight": row["text"],
            }

        for block in blocks:
            have = _normalise(block["text"])
            if wanted and (wanted in have or have in wanted):
                chosen = block
                break

    if chosen is None:
        chosen = max(blocks, key=lambda block: score(block["text"]))
        if score(chosen["text"]) == 0:
            return None

    sentences = _sentences(chosen["text"])
    best = max(range(len(sentences)), key=lambda i: (score(sentences[i]), -i))

    # About three sentences: a block of up to four is kept whole, so a
    # numbered medicine keeps its name and dose. A longer block is cut
    # to three sentences in a row that include the answering one;
    # sentences are never skipped from the middle.
    if len(sentences) > MAX_EXCERPT_SENTENCES + 1:
        start = max(0, min(best - 1, len(sentences) - MAX_EXCERPT_SENTENCES))
        sentences = sentences[start:start + MAX_EXCERPT_SENTENCES]
        best -= start

    chosen = dict(chosen, text=" ".join(sentences))

    section = chosen.get("section")

    return {
        "section": section.title() if section else None,
        "text": _block_text(chosen),
        "highlight": sentences[best],
    }


# ---------- The appointment a passage refers to ----------

# "consultant has reviewed you at your 6-week appointment": the passage points at an appointment.
_REFERS_TO_APPOINTMENT = re.compile(r"\b(?:appointment|review\w*|follow[- ]?up|clinic|consultant)s?\b", re.IGNORECASE)

# How much of a word must match, so "review" in a title finds "reviewed" in the passage.
_STEM_LENGTH = 6


def related_appointment_lines(source: dict | None, appointments: list[dict] | None) -> list[dict]:
    """
    The letter's own lines for the appointment a passage refers to.

    "Do not drive until your consultant has reviewed you" answers the question
    but not "when is that?". When the passage refers to an appointment and the
    plan holds one whose title it names ("Consultant review"), that
    appointment's line from the letter is returned to show under the passage.

    Nothing is guessed: an appointment is included only when every main word
    of its title appears in the answering sentence, the plan kept the letter's
    wording for it, and that wording is not already in the excerpt on screen.
    """

    if not source or not appointments:
        return []

    sentence = str(source.get("highlight") or source.get("highlighted_line") or source.get("text") or "")

    if not _REFERS_TO_APPOINTMENT.search(sentence):
        return []

    sentence_stems = {word[:_STEM_LENGTH] for word in re.findall(r"[a-z]+", sentence.lower())}
    # Only what the panel displays counts. The raw chunk ("passage") can hold the appointment
    # line further down without it ever being shown.
    already_shown = _normalise(" ".join(str(source.get(key) or "") for key in ("text", "highlight")))
    lines: list[dict] = []

    for appointment in appointments:
        if not isinstance(appointment, dict):
            continue

        title_words = [word for word in re.findall(r"[a-z]+", str(appointment.get("title") or "").lower()) if len(word) > 3]

        if not title_words or any(word[:_STEM_LENGTH] not in sentence_stems for word in title_words):
            continue

        letter = appointment.get("source") if isinstance(appointment.get("source"), dict) else {}
        snippet = str(letter.get("snippet") or "").strip()

        if not snippet or _normalise(snippet) in already_shown:
            continue

        page = letter.get("page")
        lines.append({"text": snippet, "page": int(page) if page is not None else None})

    return lines
