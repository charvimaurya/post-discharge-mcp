# AfterWard submission checklist

Owner-controlled checklist, 17 October 2026. Checked boxes mean verified in this
workspace/review, not published or accepted by an event. Everything external
requires its own receipt or successful access test. Start with the P0 items in
[readiness-review.md](readiness-review.md).

## P0: rules, scope and recording target

- [ ] Obtain the implementation guide reviewed **15 October 2026**; record its
  exact file/URL/version and reconcile every mandatory requirement with code,
  evidence and any approved exception. Currently **CANNOT VERIFY**.
- [ ] Record the official event URL, exact track name, rule version,
  deadline/timezone, judging criteria and submission owner. Do not infer a track
  from “Alexa+” in the repository title.
- [ ] Check native Alexa+/device requirements against **Simulated Alexa+**; if
  native integration is mandatory, simulation alone does not meet it.
- [ ] Check whether AgentCore or Polly is mandatory for the proposed track.
  The verified application path is ECS/Fargate/ALB/CloudFront with browser speech;
  an AgentCore scaffold or an AWS account does not prove those integrations.
- [ ] Confirm AWS service/model/account/region requirements, MCP/tool-server
  requirements, eligible prior work dates, external package attribution, team
  eligibility and limits, and any mandated product-feedback evidence. Mark each
  rule satisfied only with a matching artifact or an organizer's written exception.
- [ ] Choose the recording target and label it. Resolve or disclose **seven local
  versus six deployed tools**; the responding endpoint lacks undo_report, and the
  other endpoint timed out. Do not silently show a local trace as cloud execution.
- [ ] Approve an isolated synthetic demo tenant/recording environment. Shared
  patient uploads, resets and completions can affect other sessions. Do not expose
  unrestricted visitors or real patient data to obtain a submission link.

## Video: target 3:00

- [x] Prepared [timecoded script](video-script.md): problem → extraction → daily
  plan → reminder → task completion → grounded questions → real MCP evidence.
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
- [ ] Show a named task completion rather than the known ambiguous medicine-write
  failure. Disclose the workflow limitation in written materials.
- [ ] Record, add captions, review readable text/audio, measure the exported runtime,
  and verify the event's actual length/format rules. No video has been created here.
- [ ] Upload only after owner approval; verify the watch URL from a signed-out or
  judge-equivalent browser, including audio, captions, playback and privacy settings.
  Record video URL, final filename/hash and review date in the submission log.

## Devpost content and links

- [x] Prepared [local Devpost draft](devpost-draft.md); not posted.
- [ ] Obtain any existing Devpost draft and compare **every** external claim with
  the [claim ledger](readiness-review.md). Remove unsupported claims about native
  Alexa+, AgentCore, Polly, seven deployed tools, clinical benefit, production
  readiness, universal grounding or a hosted frontend.
- [ ] Confirm project name, tagline, description, team names/contributions, build
  dates, tools/services actually used, external package credits, license and any
  event-specific disclosures. Do not invent user testimonials or adoption metrics.
- [ ] Add final accessible video and repository links. Add a demo URL only if the
  actual user journey works there; an authenticated `/mcp` endpoint is not a frontend.
- [ ] Test every submitted URL in a judge-equivalent session: repo, video, demo,
  package, architecture, feedback evidence and supporting test report. Resolve
  expired links, login requirements and private preview credentials privately.
- [ ] Verify any required screenshots, architecture diagram, text/character limits,
  required fields, track selections, tags, acknowledgments and terms against the
  actual event form. Preview the final rendering and record the final page URL.
- [ ] Owner explicitly approves publication/submission; submit manually and save
  the confirmation receipt/time. Neither approval nor submission has occurred here.

## Product feedback and track evidence

- [ ] Identify which product and official feedback channel the event requires,
  and whether feedback must be public/private or submitted before the deadline.
- [ ] Draft concrete feedback from actual use, with reproducible steps and expected
  versus observed behavior. Candidate observations from this repository:
  * Amplify's documented Next support range blocks this Next 16 SSR project;
    version compatibility should be checked before configuring runtime roles.
  * Bedrock/MCP application testing benefits from separate evidence for model
    behavior, protocol traffic and durable tool effects; a passing mocked tool
    test did not establish deployed tool parity.
  * Browser speech needs explicit capability/permission fallback; it does not
    establish native Alexa+ or Polly behavior.
  These are draft engineering observations, **not customer research** and not
  evidence that a product-feedback requirement has been fulfilled.
- [ ] Owner reviews and sends feedback through the required channel only after
  explicit authorization. No feedback, email or third-party message was sent here.
- [ ] Save the required receipt/link/screenshot and date, redact private data, and
  include it in the event form if required. Record any organizer clarification.

## Tests, reliability and demo instructions

- [x] Current review: **841 Python tests passed, 10 live integrations deselected**;
  **73 web tests passed**.
- [x] Typecheck and production build passed in the preceding implementation review;
  no application code changed in this documentation review.
- [x] Final-model evaluation recorded separately: **13/14**, 19 actual Converse
  calls, configured Sonnet 4.5, synthetic in-memory tools. Failure: ambiguous
  medicine report caused a deterministic write. Do not state “all tests passed.”
- [x] Authenticated deployed **tools/list** verified six tools at one CloudFront
  endpoint; local registration verified seven. This is not an end-to-end test.
- [ ] Approve and execute a fresh final-target smoke test for upload → ready plan →
  reminder → named completion → re-read → sourced answer, using isolated synthetic
  state. The existing `scripts/test_mcp_http.py` can write completions; it is not
  a read-only health check. Capture date, code revision, model, clock and target.
- [ ] Re-run tests/typecheck/build after any application changes. If model/config
  changes, repeat the final-model plan and preserve failures/limitations.
- [ ] Verify visitor/patient isolation, shared conversation/crisis state, deployed
  quota table/IAM/proxy-IP handling and safe uploads before unrestricted access.
  The [demo test report](../public-demo-final-test-report.md) remains NO-GO.
- [ ] For a restricted recording, supply short setup/demo instructions, supported
  browser, synthetic fixture, backend target, clock mode, known limitations and
  an owner-operated reset procedure. Never give judges privileged AWS/bridge keys.

## Repository access and release snapshot

- [x] Git origin is `charvimaurya/AfterWard-A-Living-Recovery-Plan-for-Alexa`;
  MIT license exists in `LICENSE`. This does not verify remote visibility/access.
- [ ] Review the uncommitted changes and approve a commit/release snapshot. Remote
  main cannot be assumed to contain this working tree. No commit is authorized here.
- [ ] Review tracked `.venv-check/` (6,895 files), generated artifacts and the final
  secret/history scan results before any publication. No history rewrite or key
  rotation is part of this review.
- [ ] Verify `discharge-letter-check` v0.1.0 can be installed from the pinned URL
  in a fresh environment with the judge's access level. Installed package imports
  and contract tests pass locally; anonymous fetch/install was not verified here.
- [ ] Confirm repository access using the event's allowed method. If private access
  is allowed, test the authorized judge path; if public is mandatory, obtain
  separate explicit approval after security review. **Do not make public automatically.**
- [ ] Test a clean clone of the approved snapshot and document required AWS access,
  dependencies and environment variables. No access keys or service tokens in
  README examples, Devpost, video, screenshots or downloadable artifacts.

## Submission log — owner fills with actual evidence

| Item | Value / receipt |
| --- | --- |
| Guide / official rules / track | Pending |
| Deadline with timezone | Pending |
| Approved revision and code snapshot | Pending |
| Recording target / clock / model / date | Pending |
| Final video URL and measured runtime | Pending |
| Devpost URL | Pending |
| Verified repo judge-access method | Pending |
| Verified demo URL or disclosed local-demo scope | Pending |
| Product feedback receipt | Pending |
| Final owner approval and submission receipt | Pending |
