# AfterWard final repository audit

Audited 17 October 2026. Baseline: local `main` and cached `origin/main` at
`41a746473b57876d76e43f0a156bba14da33c3a0`. No fetch was performed; remote freshness
is not verified. Initial working tree was clean. The later user instruction
authorized artifact cleanup, ignore rules, frontend naming fixes and tests;
those uncommitted changes are recorded below. No AWS resources were changed,
no deployment was run, and nothing was committed.

The implementation guide reviewed on 15 October was not supplied or found in
tracked documentation. **CANNOT VERIFY** compliance with that exact guide.
This is an evidence-based audit of the requested areas, not a claim that the
missing guide's acceptance criteria have passed. `docs/REPOSITORY_GUIDE.md` is
available but contains demonstrably obsolete descriptions.

## Findings and proposed order

1. **P0: protect public entry points and isolate visitors.** The frontend and
   bridge currently use one synthetic patient without visitor authentication.
   An exposed bridge permits history deletion. Keep the current setup local
   until public access has an explicit identity and isolation design.
2. **P1: bound uploads, requests, sessions and AWS spending.** Existing per-turn
   bounds do not provide admission control or a spending ceiling.
3. **P1: make bridge deployment and fresh-clone setup reproducible.** The ECS
   configuration deploys MCP, not the bridge/agent that the frontend needs.
4. **P1: make crisis/session state and document replacement reliable across
   restarts, multiple workers and concurrent uploads.**
5. **P2: reconcile documentation, remaining repository artifacts, and public
   demo/submission evidence.** Complete the missing-guide comparison when the
   guide becomes available.

Effort estimates below are engineering person-days, excluding permission,
account provisioning and review wait times. P0 indicates a blocker to exposing
the interactive service publicly; it does not establish that a live service
is currently exposed or compromised.

## Status matrix

| Area | Status | Exact evidence and limits |
| --- | --- | --- |
| Crisis routing | PARTIAL | `app/agent/service.py:1641` routes crisis messages before agent tools/model/history; `app/agent/crisis.py:21` defines phrase matching and fixed responses. `tests/agent/test_crisis.py:73` covers direct, indirect, harm-dose and follow-up cases. Bridge `app/web_bridge.py:118` writes chat activity and reads state before calling the agent, so “nothing saved/no dependencies” applies to the agent branch, not the entire HTTP request. State-read failure can prevent the crisis reply. |
| MCP implementation | DONE | `app/mcp/server.py:84` onward registers seven recovery/search/report/undo tools; `app/mcp/http_server.py` installs stateless HTTP and host/origin checks; `app/mcp/http_auth.py` checks bearer tokens and derives patient context. `tests/mcp/` and `tests/auth/test_mcp_token.py` cover tool/context/token behavior. DONE means implemented locally, not independently verified deployed. |
| MCP patient isolation | PARTIAL | `app/mcp/context.py` uses ContextVar request scoping; `app/mcp/http_auth.py` maps every valid token to `demo_patient_001`. `app/rag/vector_store.py:query_chunks` filters both patient and current document, but vector write keys use `chunk_id` without a patient namespace. There is no visitor-specific identity mapping. |
| discharge-letter-check integration | DONE | `requirements.txt:7` and `deployment/requirements-lambda.txt` depend on v0.1.0; `app/ingestion/bedrock.py:5` loads the package schema; `app/ingestion/document_validation.py` and `app/ingestion/validator.py` re-export package functions; `app/models/recovery_model.py` imports instruction types while retaining application state. `scripts/deployment/build_document_lambda.py:31` checks package files are packaged. `tests/ingestion/test_package_integration.py` passes. Network installation and Lambda execution were not repeated. |
| Obsolete files | PARTIAL | Authorized cleanup removed confirmed inactive snapshots/builds listed below. Baseline contained 2,463 tracked files under root `lambda_package/` and 11 under `phase15/`. Latest commit also introduced 6,895 tracked `.venv-check/` files; that environment remains tracked and was used for validation. `AfterWardMCP/app/AfterWardMCP/main.py` contains arithmetic/greeting example tools rather than application tools; its deployed-state records mean it needs separate ownership review before deletion. |
| Duplicate schema | DONE | The local copy `app/ingestion/schemas/discharge-extraction.schema.json` was removed on 18 Oct. AfterWard now loads the schema only from `discharge_letter_check` (`load_schema()`), in production and in tests. |
| Secret history | CANNOT VERIFY | No tracked `.env`/`web/.env.local` history was found by path search across available refs. Pattern scans of 575 historical text blobs outside vendored site-packages found only the documented local-development token in `.env.example:29`; supplemental bearer/literal-secret and JSON environment-value scans produced no additional candidates. `.gitignore` excludes private environments. This is not a complete secret scanner: vendored content, archives, binary files, unreachable objects, remote-only refs and credential validity/rotation were not fully examined. Account IDs, hostnames and secret ARNs in deployment JSON are identifiers, not evidence of secret disclosure. |
| AWS documentation | PARTIAL | `docs/aws-integrations.md` maps ten services to code; `deployment/README.md:14` documents current Linux-compatible builder and reminder deployment; `infra/security/` contains storage/IAM controls. `docs/REPOSITORY_GUIDE.md:30` incorrectly says MCP is absent; `docs/architecture.md` describes outdated MCP/occurrence behavior. Integration overview omits the ECS/ECR/ALB/CloudFront hosting path and future Amplify/bridge setup. `docs/aws-name-migration.md:25` records earlier verification, not a current live audit. |
| Fresh-clone readiness | PARTIAL | README supplies Python setup; frontend has a lockfile and Node guidance. `app/config.py:10` requires AWS_REGION on import. `.env.example` omits required agent-client `MCP_URL` (`app/mcp/client.py:69`) and `FINAL_AGENT_MODEL_ID` (`app/config.py:14`); web example omits `AGENT_API_URL`. Root dependencies omit pytest and rely on transitive server dependencies. Dotenv pins differ between root and deployment. Existing environments passed; a clean dependency installation/container build was not performed. |
| Bridge authentication | MISSING | `app/web_bridge.py` constructs Starlette with only request logging middleware. `/chat`, `/today`, `/documents/validate`, `/documents/uploaded` and `/reminders/check` have no authentication. `web/app/api/chat/route.ts` and `web/lib/upload-validation.ts` forward request IDs but no service credential. Loopback binding in `scripts/run_web_bridge.py` limits the documented local deployment only. |
| ECS bridge deployment | MISSING | `Dockerfile` starts `app.mcp.http_server:app` on 8000; `ecs-task-definition.json` contains one MCP container. It has no bridge/agent container or service, bridge health endpoint, agent model configuration, or bridge logging configuration. `web/lib/bridge.ts:4` defaults to localhost:8002, which cannot locate the developer's bridge from hosted frontend compute. Existing ECS IAM policies allow Titan embeddings, not the conversational model, and omit EventHistory batch deletion needed by upload reset. |
| Amplify / frontend | PARTIAL | `web/app/demo/page.tsx`, API routes and voice helpers implement a functioning local interface. `web/README.md` explicitly documents local-only, unauthenticated use. No first-party Amplify build/deployment configuration, hosting-role setup, deployed frontend URL or authenticated frontend flow was found. Local tests/typecheck passed. Hosting and browser voice behavior were not verified. |
| Reset | PARTIAL | `scripts/reset_demo_patient.py` is confirm-gated, hardcoded to the synthetic patient, paginates completions and resets reminder fields. It does not clear the running bridge's conversation/crisis dictionaries. `app/web_bridge.py:document_uploaded` deletes all patient history, without a document ID or proof of upload. `web/app/api/upload/route.ts:45` invokes it immediately after S3 upload, before ingestion success; failure still returns upload success. |
| Session isolation | PARTIAL | `app/agent/session.py` bounds each history to 12 messages but stores all sessions and crisis flags in process-local dictionaries keyed only by caller session ID. No TTL, session ownership, global bound, shared persistence or per-session serialization is present. `web/app/demo/page.tsx:50` uses a tab UUID, but every visitor still shares recovery state and reminders. Changing session ID/restarting a worker loses crisis follow-up state. |
| Rate limits | MISSING | No first-party request throttling/admission middleware or WAF rate rule was found in `app/`, `web/app/`, `web/lib/`, `infra/` or `deployment/`. Agent tool-round bounds at `app/agent/service.py:163` are per turn, not a request limit. |
| Upload protection | PARTIAL | `web/app/api/upload/route.ts:16` checks extension/MIME and PDF signature, then prevalidates through the bridge. `app/ingestion/pipeline.py:process_text` validates documents again; worker rejection preserves the current plan (`app/ingestion/document_service.py:275`). No application byte/page/text bound is enforced before whole-body buffering or PDF extraction. S3 event processing has no equivalent size gate. |
| Cost controls | PARTIAL | Extraction has maxTokens=5000 (`app/ingestion/bedrock.py:156`); agent rounds and per-session history are bounded; ready-document retries are skipped (`app/ingestion/document_service.py:204`). Concurrent/incomplete retries can repeat extraction; there is no ingestion lease. No budget configuration, per-visitor quota, concurrency cap or spending kill switch was found. `infra/observability/template.yaml` provides error/DLQ alarms and explicitly says NOT DEPLOYED, not spending control. |
| Automated tests | DONE | Final local commands: `pytest -q`: **812 passed, 10 deselected**; `npm test`: **54 passed**; `npm run typecheck`: **passed**. Python used existing `.venv-check`, dummy AWS credentials, disabled metadata and cache/bytecode writes. Default pytest excludes integration tests (`pytest.ini`). These results do not prove deployment, clean installation, clinical accuracy, load behavior or browser end-to-end behavior. No CI workflow was found. |
| Public demo | CANNOT VERIFY | `ecs-task-definition.json` and `cloudfront-config.json` name an MCP CloudFront endpoint, not a public frontend. `scripts/deployment/verify_migrated_mcp.py` provides a live read/search check but was not executed. No public interactive UI URL or dated live verification artifact was found. No live writes or reminder invocations were made. |
| Devpost | MISSING | No first-party Devpost URL, submission checklist, video link or submission document was found in README/docs/web/deployment/scripts. Actual external submission status is CANNOT VERIFY. |

## Critical risks and remediation backlog

| Priority | Risk / proposed work | Effort | Dependencies / completion evidence |
| --- | --- | --- | --- |
| P0 | Public UI calls use privileged AWS/MCP access on behalf of anonymous visitors. Add frontend identity or a deliberately isolated synthetic sandbox, authenticated bridge requests, and authorization on reads/writes/reset. A service token alone does not authenticate visitors. | 2–4 days | Decide demo identity model; negative auth tests on every route and cross-visitor isolation tests. |
| P0 | Direct bridge `/documents/uploaded` can erase all shared history. Bind reset to authenticated successful document promotion; scope it to the previous document and handle concurrent ingestion safely. Stop treating S3 acceptance as plan replacement success. | 1–3 days | Identity design; document version/ownership model; failed-ingestion and upload-race tests. |
| P1 | Crisis response depends on successful bridge state read; follow-up safety is lost on restart/session change. Move dependency-free crisis interception to the request boundary and bind durable crisis/session state to the intended identity policy. Regex coverage is not a guarantee of language understanding. | 1–3 days | Identity/session model; unavailable-database, multiworker, restart and adversarial-language checks. |
| P1 | Unbounded body/page sizes, requests and session count permit resource exhaustion and repeated paid model calls. Add request/message/PDF bounds, quotas, bounded queues/concurrency, session expiry and cost alerts/stop procedure. | 2–3 days | Hosting choice, expected traffic and budget owner; reject oversized input before buffering/extraction and verify throttling without live spending. |
| P1 | Ship a bridge/agent deployment with health checks, service discovery, model access and narrowly scoped reset permissions; wire hosted frontend to it. Pin the deployed image by digest and capture environment/role requirements. | 2–4 days | P0 identity decisions, TLS/network design, model ID and execution roles. The committed CloudFront config uses HTTP to its origin; verify live network/origin restrictions before relying on it for bearer-token transport. |
| P1 | Prevent older/concurrent SQS jobs from overwriting newer plans. Add conditional document promotion/lease semantics and avoid repeating extraction on indexing-only retry. Namespace vector keys by patient and document. | 2–4 days | Document version model; out-of-order delivery and collision tests. Current `app/ingestion/document_service.py:295` and `:317` save without promotion coordination. |
| P1 | Reproduce setup from a clean checkout, including package download, Docker and Linux Lambda import. Declare direct runtime/dev dependencies, complete environment templates and resolve conflicting pins. | 1–2 days | Dependency network access and isolated test account for later deployment smoke test. Local passing tests alone are insufficient. |
| P1 | Remove tracked `.venv-check` in a separate reviewed cleanup and run a full history/archive secret scan. If real secrets are discovered, rotate first and then decide history remediation. No evidence here justifies claiming a leaked key or performing a history rewrite. | 0.5–1 day | Preserve working test environment; approval for any subsequent history rewrite. Ignore rules do not untrack existing files. |
| P2 | Update repository/architecture/setup/testing docs to describe current MCP, occurrences, external package, bridge startup, hosting and reset limits. Document ownership/status of `AfterWardMCP/`. | 1 day | Confirm intended hosting path and obtain 15 October guide. |
| P2 | Review the two local-schema tests together before removing the duplicate; preserve package schema shape and fresh-copy contract tests without a second checked-in schema. | 0.25 day | Explicitly broaden the conditional schema cleanup; currently retained. |
| P2 | Add CI for mocked Python/frontend/type checks and later synthetic browser smoke coverage. Publish verified demo/video URLs and a Devpost checklist with synthetic-data/reset instructions. | 1–2 days | P0/P1 public-hosting blockers, hosting credentials, submission owner and exact event requirements. |

## Authorized cleanup and reference evidence

Before deletion, tracked first-party text was searched with `git grep -n -I`
for each artifact and setup-script name, excluding vendored dependencies and
lockfiles. Active builder, Docker, deployment, app, frontend, infra, scripts
and tests were inspected. Documentation/history mentions were distinguished
from runtime inputs.

| Action | Evidence / reason |
| --- | --- |
| Removed `phase15/` (11 tracked files) | UI snapshot with copy-in instructions in its README; active equivalents already live in `web/`. No active first-party consumer. Its only external mention was the obsolete `output.txt` inventory. |
| Removed root `lambda_package/` (2,463 tracked files) | Vendored dependency/application snapshot. `scripts/deployment/build_document_lambda.py:55` creates fresh temporary staging, reads deployment requirements, and packages current `app/` and `lambdas/`. `build/lambda_package/` documentation refers to a different path. |
| Removed `careloop_document_processor.zip` | Old root archive, mentioned only in the obsolete inventory. Current deployment uses `build/afterward_document_processor.zip` (`deployment/README.md:28`). |
| Removed `lambda-smoke-response.json` | Saved old `rpds` import-error response, not a fixture or deployment input; no active references. |
| Removed `output.txt` | Dated codebase inventory containing old commit IDs/counts. Removed its stale tree entry in `docs/REPOSITORY_GUIDE.md`; this audit preserves current findings. |
| Removed `list_models.py` | Unreferenced standalone model-discovery utility; only the removed inventory named it. Kept documented `check_setup.py`, `verify_models.py` and `run_ingestion.py` (`docs/REPOSITORY_GUIDE.md:103`, `:146`, `:159`). No other operational scripts were deleted merely for lacking imports. |
| Retained ignored `build/` archives | Current ZIP, documented previous ZIP, and deployed/pre-rebuild snapshots may support deployment/rollback. Lack of imports does not prove operator backups unused. |
| Retained local schema | Two active test consumers, not solely the diet test. No test/schema changes made. |
| Updated `.gitignore` | Ignores `.venv*/`, retired root snapshot directories, root ZIPs and saved output artifacts. Does not remove already tracked `.venv-check` files. |
| Updated frontend naming | `web/app/layout.tsx` title is `AfterWard`; npm package is `afterward-web` in `web/package.json` and both root package names in `web/package-lock.json`. Lowercase package identifier follows npm conventions. No AWS resource names changed. |

The repository is substantially implemented and well covered by local tests,
but public hosting readiness and exact implementation-guide compliance remain
unverified. Public authentication/isolation and destructive reset handling are
the first release blockers.
