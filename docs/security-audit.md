# AfterWard security audit before publication

17 October 2026. Baseline `5160c54`; bridge hardening below is uncommitted and
not deployed. No secret values were printed. No credentials were rotated,
history rewritten, visibility changed or live resources modified. AWS calls
were read-only inventory, secret comparison/metadata and template validation.

**Recommendation: NO-GO for publishing the interactive AWS-backed application.**
Visitor authentication/isolation, broad live IAM permissions and the existing
MCP HTTP origin path remain unresolved. For source-repository publication,
no first-party credential leak was confirmed in available history, but ignored
credential-bearing files must be excluded from any archive/build/publication
and vendored scanner matches should be reviewed before declaring a clean scan.
Do not interpret this report as approval to change repository visibility.

## Credential and history checks

- Gitleaks **8.30.1**, default rules, `--redact=100`,
  `--ignore-gitleaks-allow`, archive traversal depth 2.
- `gitleaks git --log-opts=--all ...` scanned available refs in this non-shallow
  clone (23 commits). **232 findings**, all `generic-api-key`, in vendored SDK
  files under historical `lambda_package/` or the old Lambda ZIP. **Zero
  first-party history findings** by path classification. These are scanner
  matches in third-party SDK examples/implementation, not 232 demonstrated
  leaked application keys. No blanket suppression or history deletion was made.
- Historical path inventory found only `.env.example` and `web/.env.example`;
  no committed private `.env` path was found. Unreachable objects, remote-only
  branches, credentials held outside the repository and archives deeper than
  the configured traversal depth are outside this assurance.
- `gitleaks dir ...` on the local working directory found **606 matches**:
  580 in ignored `build/`, 15 in ignored `infra/security/backup/`, 10 in
  ignored `web/.next/`, and one in root `.env`. Counts include duplicate
  occurrences and generated/vendor values; they are not counts of unique keys.
- Root `.env:22` and ignored
  `infra/security/backup/name-migration/.env.before-cutover:22` contain a real
  MCP credential. Other backup findings include AWS temporary access identifiers
  in saved Lambda download responses. Generated Next cache/manifests also have
  framework-generated encryption/preview values. These local artifacts must
  never be included in a publication ZIP, build context or support upload.
- `.gitignore` excludes these private/generated paths. New `.dockerignore`
  excludes environment files, AWS/local tool directories, backups, web output,
  virtual environments and ZIPs from container build contexts. Explicit Docker
  COPY instructions copy only application code and dependency manifests.
- A read-only comparison against the MCP secret referenced in
  `ecs-task-definition.json:79` verified that it is nonempty and **differs from
  the published local example default**. It **equals the private local `.env`
  MCP token**, so developer and deployed-secret access are not separated. The
  running ECS task definition's secret value was not extracted; the comparison
  refers to the secret ARN in the committed task definition.
- Secrets Manager metadata reports rotation disabled, an AWS-managed encryption
  key, and one secret version. Reading its resource policy was denied; that
  policy's access boundaries are **CANNOT VERIFY**. Disabled automatic rotation
  alone is not evidence of a compromised credential. No rotation was attempted.

Redacted scanner reports were written under a private temporary directory,
outside the repository. No unredacted report was created.

## Findings, severity and remediation

| Severity | Finding and evidence | Remediation / status |
| --- | --- | --- |
| HIGH | Anonymous frontend callers can read the shared recovery record, chat through privileged MCP credentials, upload a replacement letter and trigger history deletion. `web/app/api/chat/route.ts`, `upload/route.ts`, `recovery-state/route.ts`, `today/route.ts`, `reminders/check/route.ts`; fixed demo identity in `app/mcp/context.py` and `app/mcp/http_auth.py:156`. | Add visitor authentication/authorization, isolated synthetic state and quotas before public exposure. The new bridge service key authenticates the frontend server only. **OPEN.** |
| HIGH | Bridge routes previously had only log middleware, including destructive `/documents/uploaded` (`app/web_bridge.py:265`). | **FIXED LOCALLY, NOT DEPLOYED:** `app/auth/bridge_auth.py` protects every non-health HTTP request with constant-time comparison; absent/blank keys fail closed and cloud keys require 32 characters. Public liveness at `/bridge/health`. Raw-client boundary tests in `tests/auth/test_bridge_auth.py`. |
| HIGH | Existing live `AfterWardEcsTaskRole` retains `SecretsManagerReadWrite`, `AmazonDynamoDBFullAccess`, `AmazonS3FullAccess`, `AmazonBedrockFullAccess`, Secrets Manager read-only and QuickSight secret policies. Document Lambda inline policies allow Bedrock/vector operations on `Resource: *`. Confirmed by read-only IAM inspection. Repository hardening policies (`infra/security/iam-ecs-task-policy.json`, `iam-document-processor-policy.json`) do not prove they have replaced live permissions. | Apply reviewed scoped policies in a separately approved change, verify effective permissions, then remove overlapping broad policies. New bridge roles in `deployment/bridge/template.yaml` are restricted independently. **OPEN ON LIVE ROLES.** |
| HIGH | `cloudfront-config.json:14` specifies HTTP-only origin transport. Live MCP ALB inventory confirms an internet-facing HTTP port-80 listener and target port 8000. If used as committed, the bearer token and recovery traffic traverse that origin leg without TLS. | Add reviewed TLS/origin restrictions and assess direct-ALB access. Do not assume HTTPS at CloudFront encrypts the origin connection. New bridge ALB accepts HTTPS only; existing MCP path is unchanged. **OPEN.** |
| HIGH | No request quotas, message/PDF byte/page limits or global session bound. `web/app/api/upload/route.ts:14` buffers form data and then the full PDF; `app/web_bridge.py:validate_document` reads the complete body; `app/agent/session.py` has unbounded session dictionaries. | Enforce admission/body/page limits before parsing, identity-based rate limits, session TTLs, concurrency/budget controls. **OPEN.** |
| MEDIUM | History reset is triggered immediately after S3 upload, before a successful new plan, and deletes every event for the patient (`web/app/api/upload/route.ts`, `app/database/event_history.py:105`). Service authentication does not make this operation document-safe. | Bind reset/promotion to authenticated document version and successful ingestion; preserve unrelated history and handle upload races. **OPEN.** |
| MEDIUM | Client-selected session IDs are not bound to an identity; crisis/history state is process-local (`app/web_bridge.py:111`, `app/agent/session.py`). Restart or a fresh session loses follow-up safety state. | Use identity-bound durable sessions, expiry and per-session serialization. Prepared deployment uses one worker/task with no overlap and documents downtime/state loss; this is not durable isolation. **OPEN.** |
| MEDIUM | Test reminder hooks are enabled in default real mode (`app/clock.py:43`), and the frontend forwards `force_next`. | Bridge stack explicitly sets production mode, and local loop is forcibly suppressed in ECS/production. Keep production mode fixed; broader fail-safe test-hook design remains follow-up work. **MITIGATED IN PREPARED CONFIG ONLY.** |
| MEDIUM | Private local `.env` uses the same MCP token as the configured deployed secret; source auth favors direct token overrides and caches indefinitely (`app/auth/mcp_auth.py:25`, `app/auth/mcp_token.py`). | Separate development/service credentials. New cloud bridge requires a secret ARN and reads it with a scoped task role; restart tasks after an independently approved credential change. Existing MCP server behavior remains unchanged. **PARTIAL.** |
| MEDIUM | Ignored local backups include credential material and old generated artifacts. Removing a tracked ZIP from HEAD does not remove its history. | Publish only a reviewed tracked-tree export; do not upload the whole local directory. Review/redact any intentionally shared backup. No key revocation/history rewrite performed. **OPEN PUBLICATION CHECK.** |
| LOW | `.venv-check/` still contains 6,895 tracked environment files, including native packages and metadata. | Remove from tracking in a separately reviewed cleanup, preserve the working local environment, and retain ignore rules. This is exposure surface and repository hygiene, not proof of a secret leak. **OPEN.** |

## MCP, IAM and browser positives

- MCP uses constant-time bearer comparison, rejects missing/invalid credentials,
  derives the synthetic patient server-side, and restores ContextVar scope in
  `finally` (`app/mcp/http_auth.py`). Host/origin checks and stateless transport
  are enabled (`app/mcp/http_server.py`). One bearer credential still grants
  the demo identity's read/write tool access; it is not visitor authentication.
- MCP secrets are referenced by ARN in the committed ECS task definition,
  rather than containing a literal production token. Secret ARNs, account IDs,
  resource names and hostnames in the repository are identifiers, not keys.
- `web/lib/aws.ts` and `web/lib/bridge.ts` import `server-only`. No `NEXT_PUBLIC_`
  credential variable or client import of these server modules was found.
  Browser responses intentionally include plan/letter evidence, so secret
  separation does not substitute for authorizing access to patient data.
- An exact-value scan of **118 existing browser bundle files** found no local
  MCP credential. A fresh production build passed and an exact-value scan of
  its **119 browser bundle files** found no synthetic BRIDGE_KEY sentinel.
  Generated server files are not public bundles; this is not a general proof
  against every possible secret value or future build configuration.
- Logging uses field allowlists and safe error types (`app/observability/log.py`,
  `app/safe_logging.py`); bridge key headers are neither returned nor logged by
  the middleware. The SVG `dangerouslySetInnerHTML` in `web/app/demo/icons.tsx`
  uses static local icon paths, not an uploaded document value.
- Source IAM scopes storage/model resources; new bridge IAM additionally
  constrains DynamoDB to the demo patient's partition. Secret injection access
  is assigned to the execution role, runtime MCP secret reads to the task role.
  Optional customer-managed secret-key permissions are separately scoped.
- S3 policy denies insecure transport and defines public-access blocking
  (`infra/security/s3-bucket-policy.json`, `s3-public-access-block.json`). Their
  live enforcement was not independently inventoried in this pass.

## Prepared bridge delivery and verification

`Dockerfile.bridge`, `deployment/requirements-bridge.txt`,
`deployment/bridge/template.yaml` and [deployment instructions](../deployment/bridge/README.md)
provide port 8002, HTTPS ALB, private Fargate tasks, health checks, non-root/read-only
execution, secret-backed authentication, logs and restricted roles. Existing
MCP deployment/resource names were not changed. Next.js callers now construct
authenticated bridge headers server-side, including validation and history reset.

- Python: **829 passed, 10 deselected** (mocked AWS; live integration excluded).
- Frontend: **56 passed**; TypeScript checking passed.
- `cfn-lint deployment/bridge/template.yaml`: passed using temporary lint tooling.
- AWS `ValidateTemplate`: **AccessDenied**; no stack/change set was created.
- Linux/amd64 bridge Docker image built successfully with fresh dependencies.
- Disposable non-root, read-only, network-isolated container: port-8002 public
  health, missing-key 503, unauthenticated 401 and authenticated validation
  routing all passed, with dummy AWS credentials only.
- Cloud inventory found no bridge in the inspected London ECS account; existing
  MCP was the only service. Other regions/compute platforms were not enumerated.

Deployment commands are documented for operator review, not executed. Public
publication remains **NO-GO** until the open high-severity risks are resolved
and the intended live configuration has been verified.
