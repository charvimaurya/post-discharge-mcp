# AfterWard submission checklist

Owner-controlled checklist. First written 17 October 2026, **updated 20 October 2026**.
Checked boxes mean verified in this workspace/review, not published or accepted by
the event. Everything external needs its own receipt or a successful access test.

**Deadline: Friday 23 October 2026, 12:00 pm PDT** (Saturday 24 October, 00:30 IST;
Friday 23 October, 20:00 BST). Nothing can be edited after this.

## Do these first (in order)

1. Rehearse and record the video, then upload it to YouTube or Vimeo.
2. Paste the Product Feedback answer from docs/product-feedback.md into the form.
3. Decide repo access (public with MIT, or private with the named judges), then test it signed out.
4. Fill the Devpost form, preview it, and submit by **Thursday 22 October** to keep a day spare.

## P0: rules, scope and recording target

- [x] Official rules read on **20 October 2026** from
  https://amazonappdev2026.devpost.com/rules. Deadline, required items, track
  rules and mini challenge fields are recorded in this file.
- [x] Track: **Alexa+**. Rule: a working self-hosted MCP server on spec 2025-11-25
  or later over Streamable HTTP, **or** a simulated Alexa+ experience in a web app.
  A simulation is allowed, but its source code must be in the repo and the video
  must clearly show it is simulated. Native Alexa+ is **not** mandatory.
- [x] AgentCore and Polly are **not** mandatory. AWS Builder accepts any AWS
  services, described inside the Product Feedback answer. Do not claim AgentCore
  or Polly unless the recorded path really uses them.
- [x] Mini challenges: **AWS Builder** and **Open Source**. A project can win at
  most one track prize and one mini challenge prize.
- [x] AWS credits: **closed** (organisers ran out on 7 October). Nothing to do.
- [ ] Obtain the implementation guide reviewed **15 October 2026** and record its
  file/URL/version. Still **CANNOT VERIFY**; the official rules above now cover
  the mandatory items.
- [ ] Confirm eligibility for both team members (age of majority, allowed country,
  no conflict of interest) and that the project was new or significantly updated
  after the submission period began. Git history is the proof.
- [ ] Choose the recording target and label it. Local and deployed now match
  (**nine tools, two prompts**, redeployed 20 Oct). Do not silently show a local
  trace as cloud execution.
- [ ] Approve an isolated synthetic demo tenant/recording environment. Shared
  patient uploads, resets and completions can affect other sessions. Do not expose
  unrestricted visitors or real patient data to obtain a submission link.

## Video: under 3:00 (rule), public on YouTube or Vimeo

- [x] Prepared [timecoded script](video-script.md): problem → extraction → daily
  plan → reminder → task completion → grounded questions → real MCP evidence.
- [x] Caption at 2:10 reads **"9 tools · 2 prompts"**. No MCPJam clip in the video
  (decided 20 Oct; the Today card is not in the demo).
- [ ] Rehearse that complete sequence on the final recording target. Verify that
  uploaded document ID matches ready state, reminder is real, completion persists,
  and the displayed source actually supports the spoken answer.
- [ ] Keep **Simulated Alexa+** and **Synthetic patient data** readable throughout.
  Label a fixed/advanced clock **Demo clock**. Label shortened processing waits.
- [ ] Test the recording browser's speech output and mic permission/recognition.
  If typing prompts, show typing honestly. Do not substitute a staged voice clip
  for a live assistant response.
- [ ] Capture actual MCP requests/results and a correlated request ID/server log.
  The UI's hardcoded protocol-version label is not negotiation evidence. Never
  expose Authorization, X-Bridge-Key, `.env`, patient data or console credentials.
- [ ] Show a **named** medicine or task completion ("I took my paracetamol"), not
  the known ambiguous "I took my tablet" case (see Tests below).
- [ ] No third-party trademarks, real hospital names or logos, or copyrighted music.
- [ ] Record, add captions, measure the exported runtime (**must be under 3:00**).
- [ ] Upload as Public or Unlisted after owner approval; check the link signed out
  (audio, captions, playback). Record the URL in the submission log.

## Devpost content and links

- [x] Final "About the project" text: [devpost-about-the-project.md](devpost-about-the-project.md)
  (merged 20 Oct: nine tools, two prompts, MCP App, Safety and guardrails section,
  "At a glance" block for judges).
- [x] Older cautious draft kept for its claim notes: [devpost-draft.md](devpost-draft.md).
- [x] **Package name fixed** (20 Oct) in devpost-about-the-project.md: it said
  `afterward-discharge-schema`, and now says **`discharge-letter-check`**
  (https://github.com/charvimaurya/discharge-letter-check, MIT, v0.1.0) in
  "How we built it" and "Accomplishments".
- [x] **Dose wording fixed** (20 Oct): the Safety section no longer claims vague
  replies block a save, and "What we learned" now names the ambiguous-dose failure
  as our next fix. This matches the 13/14 evaluation.
- [ ] Fill the "At a glance" gaps: video link, repo link
  (https://github.com/charvimaurya/post-discharge-mcp), package link (above),
  friction log link, and the test count (filled in: 1,298 Python and 145 web tests).
- [x] **Encryption and AgentCore wording fixed** (20 Oct): the Devpost text now says
  "encrypted at rest" (S3 uses SSE-S3; there is no customer-managed KMS key), and
  the AgentCore challenge gives the real reason (the starter would not deploy).
- [ ] Confirm or remove two "Challenges" items not in the friction log: the photo
  dose misread ("111" read as "171") and the S3 test message breaking the worker.
- [x] Use **one title everywhere**: "AfterWard: The Alexa+ Recovery Companion That Speaks First" (README heading, Devpost project name).
  Set it in the Devpost project name field, because Devpost builds the
  "What's next for…" heading from that field.
- [ ] Elevator pitch (tagline): "Discharge is one moment. Recovery happens every
  day. AfterWard turns a discharge letter into a daily plan that updates as you
  recover." Check it fits the form's character limit.
- [ ] "Built with" tags: python, typescript, next.js, mcp, amazon-bedrock, claude,
  amazon-s3, amazon-s3-vectors, amazon-sqs, aws-lambda, amazon-dynamodb,
  amazon-ecs, aws-fargate, amazon-eventbridge, amazon-cloudwatch, amazon-cloudfront,
  discharge-letter-check. Only tags for things really used.
- [ ] Gallery: architecture diagram (`afterward-architecture.png`) plus 2 to 3
  clean screenshots (Today screen, letter evidence highlight, Developer view).
  No tokens or keys on screen.
- [ ] Add a demo URL only if the real user journey works there; an authenticated
  `/mcp` endpoint is not a frontend.
- [ ] Test every submitted URL signed out: repo, video, package, friction log.
- [ ] Owner explicitly approves, submits manually, and saves the confirmation
  receipt and time.

## Product feedback (required) and AWS Builder

The rules ask, **for each tool, API or SDK used**:
which ones and for what; what worked well; what needs work; onboarding from zero
to hello world; would you build with it again (yes/no and why). The AWS Builder
entry is judged from the AWS part of this same answer.

- [x] Feedback goes in the **Devpost form**, not a separate channel or email.
- [x] Drafted in `docs/product-feedback.md` (20 Oct): AWS Builder table at the top,
  every tool answers all five questions, claims taken from the friction log and
  aws-integrations.md. Paste it into the Devpost form.
- [ ] Optional bonus (up to 10%): paste friction log entries in the required shape
  (task, steps, expected vs actual, severity, workaround, suggestion).
- [ ] Optional: feature requests with description, why it matters, and priority
  (Critical, Important or Nice-to-have).

## Open Source mini challenge

- [x] Package: **discharge-letter-check** v0.1.0, MIT, used by AfterWard for every
  letter, 149 tests on Python 3.11 to 3.13 in GitHub Actions.
- [x] "Open Source description" text drafted in [devpost-draft.md](devpost-draft.md).
- [ ] Form fields: contribution URL, project repository URL, GitHub username.
- [ ] Confirm the package repo is public and installs in a fresh environment
  without login.
- [ ] Confirm it was created inside the hackathon window (repo creation date).

## Tests, reliability and demo instructions

- [x] Latest recorded run: **1,298 Python tests and 145 web tests passed**
  (10 live AWS tests run separately). Re-run before quoting a number.
- [x] Final-model evaluation: **13/14**, Claude Sonnet 4.5, 19 real Converse calls.
  The one failure: an ambiguous "I took my tablet" was recorded without asking
  which medicine. Do not state "all tests passed".
- [x] 20 Oct: ECS redeployed; authenticated deployed tools/list shows nine tools
  and two prompts.
- [ ] Approve and run a fresh final-target smoke test: upload → ready plan →
  reminder → named completion → re-read → sourced answer, with isolated synthetic
  state. `scripts/test_mcp_http.py` writes completions; it is not a read-only check.
- [ ] Re-run tests, typecheck and build after any application change. If the model
  or config changes, repeat the final-model evaluation and keep failures listed.
- [ ] Testing access must stay **free and open until judging ends (20 Nov 2026)**.
  Judges may judge from text and video alone, so the README "How judges can test"
  section must work from the repo without our AWS keys.
- [ ] Verify visitor/patient isolation, shared conversation/crisis state, quota
  table/IAM/proxy-IP handling and safe uploads before any unrestricted access.
  The [demo test report](../public-demo-final-test-report.md) remains NO-GO.

## Repository access and release snapshot

- [x] Git origin is `charvimaurya/post-discharge-mcp`; MIT license exists in
  `LICENSE`. This does not verify remote visibility.
- [ ] Choose the access method allowed by the rules:
  **public** with the MIT license showing in the repo About box, **or private**,
  shared as collaborator with `knmeiss`, `giolaq`, `anishamalde`, `mosesroth`,
  `emersonsklar` and the Amazon contact address on the rules page. Public is the
  planned last step; do it only after the security review below.
- [ ] Review uncommitted changes and approve a release snapshot. Remote main
  cannot be assumed to match this working tree.
- [ ] Remove tracked `.venv-check/` (6,895 files) and generated artifacts, and
  run a final secret/history scan before publication.
- [ ] Test a clean clone of the approved snapshot and the README setup steps.
  No keys or tokens in the README, Devpost, video, screenshots or downloads.

## Submission log — owner fills with actual evidence

| Item | Value / receipt |
| --- | --- |
| Official rules / track | https://amazonappdev2026.devpost.com/rules · Alexa+ · read 20 Oct 2026 |
| Mini challenges | AWS Builder, Open Source |
| Deadline with timezone | 23 Oct 2026, 12:00 pm PDT |
| Approved revision and code snapshot | Pending |
| Recording target / clock / model / date | Pending |
| Final video URL and measured runtime | Pending |
| Devpost URL | Pending |
| Verified repo judge-access method | Pending |
| Open Source contribution URL | https://github.com/charvimaurya/discharge-letter-check (access test pending) |
| Verified demo URL or disclosed local-demo scope | Pending |
| Product feedback (in Devpost form) | Pending |
| Final owner approval and submission receipt | Pending |
