# Amplify SSR preparation

Status: configuration prepared, not deployed. **Deployment blocked:** the installed
Next.js 16.3.8 exceeds AWS's documented Amplify managed SSR support (12–15),
reviewed 17 October 2026. `npm run check:amplify` deliberately fails before any
cloud build. A successful local Next build does not establish Amplify support.
Choose and test a supported Next/React migration, or wait for AWS to document
support and review/update the guard. No dependency downgrade was performed.

References: [SSR support](https://docs.aws.amazon.com/amplify/latest/userguide/ssr-amplify-support.html),
[Node runtimes](https://docs.aws.amazon.com/amplify/latest/userguide/ssr-supported-features.html),
[SSR environment](https://docs.aws.amazon.com/amplify/latest/userguide/ssr-environment-variables.html),
[compute roles](https://docs.aws.amazon.com/amplify/latest/userguide/amplify-SSR-compute-role.html).

## Build configuration

Use repository-root `amplify.yml`, monorepo application root `web`, and console
variable `AMPLIFY_MONOREPO_APP_ROOT=web`. Select an SSR application (`WEB_COMPUTE`),
not a static export. Build and runtime use Node 24 (`web/.nvmrc` and engines).
The artifacts are `.next`, not `out`. Do not add a catch-all SPA rewrite that
intercepts `/api/*`; retain Amplify's managed Next SSR routing.

Build runs clean npm install, compatibility guard, explicit runtime env generation,
tests, typecheck and build. Neither credentials nor the generated env file are
cached explicitly. The env file contains configuration and a secret ARN, never a
secret value. Do not cache or publish `.env.local` or console/environment dumps.
The SDK resolves secrets at request time using the compute role and caches the
bridge credential for at most five minutes. Failed refreshes fail closed.

Configure these non-secret build values explicitly:

| Variable | Required value |
| --- | --- |
| AFTERWARD_AWS_REGION | Region containing S3, DynamoDB and the bridge key secret |
| DOCUMENT_BUCKET | Existing ingestion bucket name |
| RECOVERY_STATE_TABLE | Existing RecoveryState table name |
| TEST_PATIENT_ID | `demo_patient_001` for the supplied IAM policy |
| AGENT_API_URL | Reachable HTTPS bridge origin, no path or credentials |
| BRIDGE_KEY_SECRET_ARN | Exact ARN of a dedicated Secrets Manager plaintext bridge key |
| APP_ORIGIN | Exact HTTPS Amplify branch URL or canonical custom domain origin |

The writer sets `AFTERWARD_RUNTIME=amplify`. Do not set `BRIDGE_KEY`, MCP credentials,
AWS access keys, AWS secret keys or session tokens in Amplify console variables.
Do not prefix private settings with `NEXT_PUBLIC_`. Build-service role credentials
may be supplied automatically by AWS; the writer excludes them from the runtime
artifact. Give the build role no application data/secret access. The compute role
is separate and receives only the policy below.

## Compute role and permissions

`compute-trust.json` follows AWS's documented Amplify service trust principal.
`compute-policy.json` grants only S3 PutObject for UI PDFs in the demo patient
prefix, DynamoDB GetItem for that patient partition, and GetSecretValue for one
bridge key. No ListBucket, DeleteObject, Scan, Query, PutItem, MCP token access or
Bedrock permission is needed by these Next routes. Replace every `<...>` placeholder;
never attach the unresolved template. Match the key ARN and region exactly. A
custom patient requires coordinated policy/configuration changes.

For customer-managed encryption keys, add `kms:GenerateDataKey` for the upload
bucket key and `kms:Decrypt` for the secret key (and bucket key if required by the
bucket's encryption flow), scoped to exact key ARNs with `kms:ViaService` limited
to the corresponding regional service and encryption-context conditions. No KMS
grant is included for AWS-managed/default keys. Confirm bucket policy and existing
S3 event ingestion; these files do not create a new bucket or change notifications.

After deployment approval and the compatibility blocker is resolved, create a
role with the reviewed trust policy, attach the substituted policy, and associate
it with **only the intended branch's SSR compute role** in Amplify. Do not grant
this role to pull-request previews or untrusted branches, particularly with a
public source repository. Disable automatic unreviewed production builds. Example
commands below change AWS and are documentation only; none have been executed:

```sh
aws iam create-role --role-name AfterWardAmplifyCompute --assume-role-policy-document file://deployment/amplify/compute-trust.json
# Prepare /tmp/afterward-amplify-policy.json by replacing all policy placeholders.
aws iam put-role-policy --role-name AfterWardAmplifyCompute --policy-name AfterWardRuntime --policy-document file:///tmp/afterward-amplify-policy.json
# Associate the role ARN in Amplify > intended branch > SSR compute role.
# After branch settings, HTTPS and access controls have been reviewed:
aws amplify start-job --app-id <APP_ID> --branch-name <BRANCH> --job-type RELEASE
```

## Route/security review

| Route | Bridge/AWS action | Protection |
| --- | --- | --- |
| POST `/api/chat` | POST `/chat` | Server-generated key headers; message/session size checks; response field allowlist |
| GET `/api/today` | GET `/today` | Server-generated key headers; response field allowlist |
| POST `/api/reminders/check` | POST `/reminders/check` | Server-generated key headers; production force-next forbidden |
| POST `/api/upload` | POST `/documents/validate`, S3 PutObject, POST `/documents/uploaded` | Both bridge calls authenticated; PDF validation; 4 MiB file limit |
| GET `/api/recovery-state` | DynamoDB GetItem | Configured patient only; compute-role credentials |

All routes use Node runtime and force dynamic rendering. `lib/bridge.ts` and
`lib/aws.ts` import `server-only`; no client component receives credentials.
Production endpoints must be HTTPS. Bridge fetches reject redirects, use no-store
and a 25-second timeout; secret retrieval has a five-second timeout. Upstream
headers/error bodies are not forwarded or logged. Successful JSON is allowlisted
and reflected bridge keys redacted recursively. Upload-validation errors are
fixed public messages. AWS errors are fixed public messages without SDK details.

Browser calls remain same-origin; no bridge CORS permission or wildcard CORS is
needed. Requests with a foreign Origin or cross-site Fetch Metadata are rejected.
Missing Origin is accepted for server clients: this is **not visitor authentication**.
`APP_ORIGIN` must match the actual canonical domain; alternate domains need redirect
configuration. Bridge service authentication does not isolate patients/sessions.

## Remaining publication and infrastructure gates

* The live bridge endpoint and its TLS reachability are not established by these
  files. The prior ECS inspection found only the MCP service, with HTTP ALB routing.
  Follow `../bridge/README.md` for a separately approved bridge deployment. Standard
  Amplify SSR must reach a supported HTTPS endpoint; do not assume private VPC
  connectivity or a fixed egress address, and do not widen security groups blindly.
* Use a distinct production bridge key stored as plaintext SecretString; do not
  reuse local defaults. Equality/rotation against live configuration has not been
  verified for this new key. Do not expose the MCP token to Amplify.
* Anonymous routes share a demo patient, including upload/history reset. Public
  release remains NO-GO until visitor access and session/patient isolation or an
  explicitly access-controlled synthetic-data demo are implemented.
* File/declared-body checks do not bound multipart parsing with omitted/forged
  Content-Length. Add edge request-size limits, rate quotas, upload quotas and
  budget alerts before anonymous access. Shared quota infrastructure is supplied below but has not been deployed. S3/DynamoDB request timeouts and processing latency also need
  deployed smoke tests; bridge validation can exceed Amplify's request budget.
* Review preview access, HTTPS redirects, custom domain, CloudWatch log retention,
  IAM policy simulation and actual SSR compute-role credentials after approval.
  Local tests do not verify deployed IAM, secret values, CORS or TLS configuration.

## Local verification (17 October 2026)

* `cd web && npm test`: 65 passed, including secret-provider, response-redaction,
  origin, HTTPS, runtime-env allowlist and upload authentication/error tests.
* `npm run typecheck`: passed.
* `npm run build`: passed with Node 24.21.0 / Next 16.3.8; all five API routes
  remain dynamic. Rebuilt with a synthetic BRIDGE_KEY sentinel, then scanned all
  119 browser assets against the sentinel and available local credential values:
  zero matches. No secret values were printed.
* `npm run check:amplify`: intentionally failed for unsupported Next major 16.
* IAM documents parse as JSON; `git diff --check` passed. IAM authorization was
  not simulated or deployed. No Amplify builds or live resource changes ran.

The local build emits an existing warning about an unrelated package-lock.json
outside the repository. No external workspace files were modified.

Earlier verification counts above predate this follow-up; current results are in
the final demo test report linked below.

## Public demo abuse controls (17 October follow-up)

All five public API routes now pass through `web/lib/demo-guard.ts`. Cloud mode
requires a shared DynamoDB counter table and a verified trusted proxy chain;
missing configuration, counter outages and permission errors return 503 before
bridge/model/upload work. Local development uses process memory only.

Prepare `demo-limits.yaml` as a separate, approved CloudFormation stack. It creates
an encrypted on-demand DynamoDB table with `counter_key` (string hash key),
`expires_at` TTL, retention and point-in-time recovery. No stack was deployed.
Substitute its output name into `DEMO_LIMIT_TABLE` and its ARN into the compute
policy's `<DEMO_LIMIT_TABLE>` resource. The compute role needs only UpdateItem on
that table, restricted by `dynamodb:EnclosingOperation=TransactWriteItems`.
Runtime env generation now also requires `DEMO_TRUSTED_PROXY_HOPS` (1–5).

Before choosing that hop count, inspect the real Amplify forwarding chain using
a controlled request and verify that the selected right-hand X-Forwarded-For
address is the viewer IP; confirm viewer-supplied leading entries cannot change
it. CloudFront appends the actual viewer address, but an additional proxy changes
the required index. Never assume a chain from a local test or trust a viewer's
leftmost XFF entry. Block any direct-origin bypass. Until verified, leave the
cloud demo inaccessible. See [CloudFront forwarding behavior](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/RequestAndResponseBehaviorCustomOrigin.html).

Limits are fixed UTC windows: 30 chats/session/hour, 100 chats/IP/hour; three
upload attempts per signed 24-hour session, ten/IP/hour; reset reservations
three/session/hour and ten/IP/hour in the same atomic upload transaction.
Polling reads share 60/session/minute and 300/IP/minute; reminder checks allow
60/session/hour and 200/IP/hour. Failed attempts consume quota. 429 responses
include Retry-After; outages never fall back to per-instance counters.

The browser cannot select the agent session ID: a signed HttpOnly, Secure,
SameSite=Lax cookie supplies it. Signing/IP hashing derives from the bridge key
with a purpose prefix. Clearing cookies creates a new anonymous session; the IP
quota remains, but proxies/botnets can evade IP limits. Key rotation invalidates
cookies and changes hashed IP buckets; plan a protected maintenance window.
These controls do not provide patient isolation, distributed conversation
history, WAF protection or a hard AWS cost cap. See the [final test report](../../docs/public-demo-final-test-report.md)
and [budget instructions](../../docs/aws-budget-alerts.md).
