# Final hackathon submission readiness review

> **Superseded on 20 Oct 2026:** deployed and local both have 9 tools and 2 prompts; the latest run is 1,264 Python and 138 web tests. See [checklist.md](checklist.md) for the current status.

17 October 2026. Reviewed working tree on `main`, HEAD `5160c54`; many changes,
including bridge/Amplify/security/demo controls, remain uncommitted. This is not
an attestation that the remote main branch contains the current implementation.

## P0 blockers first

1. **Local/deployed MCP drift.** Local tools/list registers **seven** tools. An
   authenticated, read-only CloudFront tools/list returned **six**, without
   `undo_report`. The other CloudFront endpoint timed out after 20 seconds.
   Do not claim seven deployed tools, deployed undo, or that both endpoints work.
   Choose the recording target, resolve/version the difference with approval,
   or explicitly disclose the narrower deployed capability.
2. **Full demo is not verified.** An active ECS MCP service is not a verified
   hosted browser → bridge → agent → MCP → data journey. There is no supplied
   frontend URL or current clean-browser recording. Amplify/bridge configurations
   are prepared, not deployed; Next 16 exceeds the documented managed Amplify
   support range used by the deployment guard. Record a rehearsed local demo with
   its actual backend labelled, or verify a supported hosted setup after approval.
3. **Exact guide and eligibility are unavailable.** The implementation guide
   reviewed 15 October, official event/track rules, deadline/timezone, product
   feedback requirement and existing Devpost draft were neither supplied nor found.
   Requested them; no response available at review time. Compliance with that
   exact guide, native Alexa+/AgentCore/Polly requirements, or any track is
   **CANNOT VERIFY**. A simulated experience does not establish native integration
   eligibility. Do not choose a track based on this repository's title alone.
4. **Judge access and release artifact are unverified.** Origin is the GitHub
   repository linked below, but no authenticated visibility check or clean judge
   access test succeeded. `gh` is unavailable; browser fetches were cache misses,
   not proof of public/private status. The current work is uncommitted, 6,895
   `.venv-check/` files remain tracked, and earlier security findings remain open.
   Obtain owner review and an approved submission snapshot/access method. Do not
   make the repository public automatically or share credentials in Devpost.
5. **Unrestricted public demo is unsafe.** Visitors share a patient and resets;
   conversation/crisis state is process-local. The final-model evaluation has
   one medication-recording policy failure. Use an approved isolated synthetic
   recording; retain the public NO-GO in the [final test report](../public-demo-final-test-report.md).

## Evidence obtained in this review

Read-only AWS calls confirmed service `afterward-mcp-service` in
`afterward-cluster`, status ACTIVE, one running task, revision `afterward-mcp:5`,
launch type FARGATE, container port 8000 and target group `afterward-mcp-tg`.
CloudFront distributions `E1G5Y3L9QK930` and `E1SEY0O6MW9CTW` report Deployed and
both reference `afterward-mcp-alb-426611083.eu-west-2.elb.amazonaws.com`.

| MCP endpoint | Authenticated tools/list on 17 October | Interpretation |
| --- | --- | --- |
| `https://dakpc9juquqks.cloudfront.net/mcp` | **6 tools returned** | MCP transport/auth/listing works for this request only |
| `https://d172fd1qdqwwsa.cloudfront.net/mcp` | **Timeout after 20 seconds** | Availability not established; no root cause inferred |
| Current local `app/mcp/server.py` registration | **7 tools returned** | Implementation, not cloud parity |

The six deployed tools are get_recovery_plan, get_today_tasks, get_medications,
search_discharge_instructions, report_task_completed and report_medication_taken.
Local code adds undo_report. No patient read, completion, upload, reminder or reset
was invoked by the live checks. An ECS ACTIVE status or CloudFront Deployed status
alone would not establish application behavior. No AgentCore runtime inventory
was performed; the conclusion is that the **verified application path uses ECS**,
not that no AgentCore resources exist anywhere in the account.

## README and proposed Devpost claim ledger

No original Devpost draft was found, so its exact external claims cannot be
verified. The [new local draft](devpost-draft.md) uses the qualified wording below;
it has not been posted. All material claims in the entry README, local frontend
README, linked architecture/integration pages and the AgentCore README were
reviewed. Generated dependency READMEs and every historical setup command were
not independently executed.

| Claim | Verdict and exact evidence | Submission wording / action |
| --- | --- | --- |
| Reads letters into a structured recovery plan | DONE in code: `app/ingestion/pipeline.py`, `normalizer.py`, `bedrock.py`, `lambdas/document_processor/handler.py` | “Prototype turns discharge instructions into a recovery plan.” No clinical outcome or current end-to-end deployment claim |
| Uses AfterWard AWS names | PARTIAL: config and migration record, plus current ECS/ALB names | Describe configuration/current verified resources; rollback inventory was not refreshed |
| Original resources remain available for rollback | CANNOT VERIFY current availability; `docs/aws-name-migration.md` is dated history | README now attributes this to the migration record |
| DOCUMENT_BUCKET plus AFTERWARD_BUCKET fallback | DONE in Python `app/config.py:19`; web uses DOCUMENT_BUCKET only | README now distinguishes the two |
| Lambda ZIP builder / build excluded from Git | DONE as source/config: `scripts/deployment/build_document_lambda.py`, `.gitignore`; zero tracked `build/` files | Builder is implemented; no fresh Lambda ZIP build/deployment in this review |
| Fresh clone runs from README | PARTIAL: requirements/config commands present; needs AWS resources/credentials, package availability and matching auth | No offline/zero-setup promise. The documented MCP smoke script **writes a task** if one is pending; added an explicit warning |
| App/MCP/Lambda/deployment/test directory map | DONE by file inspection | Retained |
| “MCP server not implemented” in repository guide | FALSE/stale: `app/mcp/server.py:84` onwards registers tools, authenticated HTTP in `app/mcp/http_server.py` | Corrected stale guide passages |
| Medication/task readers have no dated occurrences | FALSE/stale: `app/database/recovery_state.py:get_medications`, `get_today_tasks`, discharge/end gates and Event History | Corrected architecture page |
| Seven MCP tools | DONE locally, **six deployed** as above | Always qualify the target/version; do not count scaffold greeting/arithmetic examples |
| AgentCore hosts the application | NOT ESTABLISHED; `Dockerfile`, `ecs-task-definition.json`, live ECS/CloudFront evidence identify the active path | Say CloudFront → ALB → ECS/Fargate. Added scope warning to `AfterWardMCP/README.md`; its independent history is not erased |
| Polly provides the voice | FALSE for active app: `web/lib/voice.ts:6`, `:39` and `web/lib/speech.ts` use browser APIs; no active Polly caller found | Say browser speech synthesis/optional recognition; availability depends on the browser/provider, not proven offline/on-device processing |
| Native Alexa+ integration | NOT ESTABLISHED: `web/app/demo/parts.tsx:16`, `:23` and assistant page label Simulated Alexa+ | Persistent **Simulated Alexa+** label in video and Devpost |
| discharge-letter-check integration | DONE locally: both requirements pin v0.1.0; installed package reports 0.1.0; `app/ingestion/bedrock.py:5`, `document_validation.py:3`, `validator.py:3`, `app/models/recovery_model.py:9` use package APIs | Package supplies schema/types/validators; AfterWard supplies AWS orchestration, agent, retrieval and reminder behavior. Four integration contract tests pass in full suite |
| All duplicate schemas removed | FALSE: local schema remains used by two tests, including `tests/ingestion/test_package_integration.py:56` | Do not make this cleanup claim |
| Answers are grounded / no guessed dose or dates | PARTIAL: evidence selection and plan checks in `app/agent/evidence.py`, `service.py`; sampled final-model probes passed | “Shows supporting letter passages; unknown end dates are not filled in in the demonstrated case.” No blanket hallucination-free/clinical-safety claim |
| Reminders and progress are implemented | DONE locally: `app/reminders/engine.py`, Lambda handler, report tools and `web/app/demo/page.tsx` | Demonstrate on synthetic state; live scheduling/end-to-end browser writes were not retested |
| Reminders run every five minutes in production | Configured, not reverified live this turn; `deployment/reminder-schedule-target.json` and deployment docs | Say scheduled Lambda checks are supported; label any recording clock acceleration |
| IAM is least privilege / public demo production ready | FALSE as a general deployed claim; earlier broad live-role/TLS findings and shared patient remain open | Prepared scoped policies are not the deployed security state |
| UI uses “MCP spec 2025-11-25” | CANNOT VERIFY negotiation: `web/app/demo/parts.tsx:400` hardcodes that label | Do not cite this UI string as protocol verification; use actual captured client/server evidence if claiming a version |
| Every test passes | FALSE for final-model plan; see results below | Report suites and evaluation separately |
| Frontend/public demo is deployed and works | CANNOT VERIFY; no frontend URL or current full recording | Mark hosted frontend pending; MCP endpoint is not the demo URL |

## Tests and known limitations

Reran this review: **841 Python tests passed, 10 live integrations deselected**;
**73 web tests passed**. Previous completed checks for the same application work
passed web typecheck and production build; no application code changed in this
review. The existing final-model run remains **13/14**, with 19 actual Converse
calls against `eu.anthropic.claude-sonnet-4-5-20250929-v1:0`. It used synthetic
in-memory tool data, not deployed MCP. The “I took my medicine” case wrote the one
remaining morning medicine without explicit naming: a deterministic policy risk,
not a passing safety check. Do not merge that run with deployed tools/list evidence
and call it an end-to-end test. See [actual case data](../agent-final-evaluation.json).

External GitHub/package page fetches were unsuccessful (tool cache misses);
this does not prove repository privacy, broken links or a missing package tag.
The package is installed and imported locally; clean remote installation and judge
access remain unchecked. No native Alexa device, Polly output, AgentCore runtime,
real patient, user study, clinical benefit, accessibility certification or deployed
multi-tenant isolation was verified.

## Proposed submission order

1. Obtain the 15 October guide/rules/track and any existing Devpost text; reconcile
   mandatory requirements with the simulated scope before investing in a recording.
2. Choose an isolated recording target and resolve/disclose the six/seven-tool
   drift. Rehearse the complete story and capture real tool traces with synthetic
   data; use the [three-minute script](video-script.md).
3. Review the current work, security/publication risks and tracked environment;
   create an approved reproducible submission snapshot. Verify reviewer access.
4. Fill video/demo/repo/package links, product-feedback evidence and exact track
   checklist. Review the [Devpost draft](devpost-draft.md) against captured evidence.
5. Owner completes the [submission checklist](checklist.md), approves any publishing
   or deployment separately, then submits manually. Nothing has been published here.
