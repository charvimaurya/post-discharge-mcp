## discharge-letter-check: the safety gate between an AI model and a patient's recovery plan

**In one line:** an open-source Python library that checks what an AI pulled out of a hospital discharge letter, and flags anything a person must confirm, so a recovery assistant never guesses a dose or a date.

🔗 https://github.com/charvimaurya/discharge-letter-check · MIT · Python 3.11+ · no runtime dependencies beyond the Python standard library

### The problem
AI models are good at reading discharge letters, but they make quiet mistakes: a dose they could not read, a missing field, two dates for one appointment, or a diet rule that was never in the letter. In a recovery plan, a confident wrong answer is worse than no answer. Prompts alone cannot guarantee the model behaves, so we wanted **plain, testable rules** that check its work every time.

### What we did
We built this checker inside AfterWard, our recovery companion for Alexa+. Then we **split it out into its own MIT-licensed package**, so any team building on discharge letters can inspect it, test it and reuse it without adopting our app or our AWS setup.

Our rule: **when something is unclear, keep the doubt visible. Never invent an answer.**

### How it works
It runs **after** AI extraction. It does not read PDFs, and it does not call any model or network service, so the same input always gives the same result.

1. **Is this a discharge letter?** `validate_discharge_document()` rejects text that does not look like one (`WrongDocumentError`), before any extraction cost is spent.
2. **Flag, never fix.** `validate_recovery_plan()` checks medicines, tasks, appointments, restrictions, monitoring, warning signs and allergies, and sets `needs_confirmation = True` when:
   - a field carries an uncertainty marker, such as `[?1 or 2 tablets?]` or `[unreadable]` (the marker is kept in the text);
   - a required field is empty, such as a medicine with no name or a warning sign with no action;
   - an appointment has **conflicting dates** (all dates are kept; none is chosen);
   - a warning sign has an unknown urgency.
3. **Check against the letter itself.** When the letter text is supplied, a diet line or a "do this after that" link whose wording is **not in the letter** is removed. Matching ignores case, punctuation and line breaks, so text that wraps across PDF lines still matches.
4. **Absence is not an error.** A missing optional detail, such as an end date, is never filled in, and it never hides the medicine.
5. **A flag is never cleared** by the checker. "Ready" means the checks ran, not that nothing was flagged.
6. **A reusable schema.** `load_schema()` gives the JSON schema the AI is asked to follow. Typed dataclasses (`RecoveryState`, `Medication`, `Task` and more) hold the checked data.

### Used in AfterWard
AfterWard installs the package from its **v0.1.0 release** (13 October 2026) and calls it on **every letter** in our AWS pipeline:

S3 → SQS → Lambda → Amazon Bedrock (Claude) extracts → **discharge-letter-check validates** → DynamoDB → 9 MCP tools → simulated Alexa+ and a classic Alexa skill.

Because the rules live in a separate package, we can test them without AWS, Bedrock or Alexa.

### Built to be trusted and extended
- **Tested on every push:** GitHub Actions runs the tests on Python **3.11, 3.12 and 3.13**.
- **A runnable example:** `examples/check_sample.py` checks a synthetic letter and shows the result.
- **Open-source basics:** a README with a public API table, `CHANGELOG.md`, `CONTRIBUTING.md` and the MIT license.
- **Next release (unreleased, on `main`):** an optional allergies list (flagged, never dropped), a schema version number, and stricter HH:MM clock times for tasks.

Try it in 30 seconds:
`pip install "git+https://github.com/charvimaurya/discharge-letter-check.git"`

### Why it matters
More and more apps let AI read medical documents. Developers need more than good prompts: they need rules they can **read, test and reproduce**. This package gives them a small, auditable gate between "the AI said so" and "the patient sees it". **AI understands the letter; plain code decides what is safe to show.**

### Honest limits
It is a prototype, **not a medical device**, and it is not clinically validated. It checks text and structure, not whether a dose or drug is medically right, so a confidently wrong extraction can pass unflagged. It has been tested on synthetic letters only.

**Next:** an "other instructions" section, so no line of a letter is silently dropped. This is how our emergency phone number was lost in an early version, and it is the main gap we are closing next.
