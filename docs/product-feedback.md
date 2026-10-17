# Product feedback from engineering

Prepared 17 October 2026 from actual repository work and recorded tests. This is
internal engineering feedback, not patient research, clinical validation, a user
survey or proof that feedback was submitted to an external product team.

| Area | Observed friction and evidence | Product feedback | Status |
| --- | --- | --- | --- |
| MCPJam App discovery | In Inspector 3.16.1 the Tools response pane returned JSON and directed users to Chat. The real App rendered through Chat/Playground Run. See [friction log](friction-log.md). | Provide a direct App preview affordance and explain which pane supports App rendering beside the result. | Rendering observed; feedback not sent. |
| MCPJam tool selection | The launch announcement covered the eighth tool row during [S5 validation](s5-implementation-report.md). Dismissing it enabled selection. | Keep announcements outside tool-list hit targets or automatically collapse them while inspecting tools. | Workaround verified; no application change. |
| MCP Apps result lifetime | MCPJam created independent App instances for weekly and Today calls. The weekly tool needed a self-contained Today snapshot. See [S5 contract](s5-implementation-proposal.md). | Document App instance lifetime and provide examples for multiple tools sharing one resource. Resource metadata alone should not imply merged results. | Independent instances verified in a real host with memory storage. |
| MCP Apps timezone | Initial host context used Los Angeles; later isolated checks explicitly selected London. Completion display followed the host context. | Make host timezone visible beside timestamps and easy to change before recording. | London-context rendering verified; earlier captures remain historical. |
| Python MCP result format | Installed SDK returns JSON text for these tools; the App also supports structuredContent. [Tests](../tests/mcp/test_today_app.py) exercise both. | Include SDK-version-specific response examples and show fallback parsing in App tutorials. | Automated checks and actual host rendering pass. |
| Shared synthetic demos | Earlier completion changed from 1/7 to 2/7, then later reads returned 1/7 without established attribution. [Isolated tests](s4-isolated-validation.md) avoided shared data and produced stable reads. | Offer isolated demo sessions, clear reset ownership and request/event tracing. Label storage type in validation reports. | Memory-backed repeatability passed; shared-backend regression unresolved. |
| Reusable checker contract | The v0.2.0 source probe failed three integration checks because application-owned state and schema assumptions had drifted. See [package review](discharge-letter-check-review.md). | Publish migration guidance and versioned contract fixtures covering caller-owned state, not only package dataclasses. | v0.1.0 remains pinned; upgrade deferred. |
| Medication confidence | Missing dose and uncertain timing can remain unflagged; stopped status is lost by application normalization. See [safety findings](discharge-letter-check-review.md#medication-safety-findings). | Distinguish extraction confidence, validation completion and clinical confirmation in APIs/UI. Preserve stop orders and require explicit identity confirmation for medication writes. | Patient-facing blocker; no clinical safety claim. |
| AWS encryption evidence | Live metadata showed SSE-S3 and SQS-managed encryption while repository files propose customer-managed KMS. See [AWS integrations](aws-integrations.md). | Label planned versus deployed controls, and provide verifiable metadata checks beside deployment recipes. | Documentation corrected; no infrastructure changes. |

## Suggested priority

First resolve stopped-order preservation and ambiguous medication-recording policy.
Next improve demo isolation and migration contracts. App discoverability, timezone
visibility and SDK examples would reduce integration and recording friction.

## Submission tracking

External product feedback destination: **PENDING_FEEDBACK_DESTINATION**.
Submission URL or receipt: **PENDING_FEEDBACK_RECEIPT**.
Do not mark a track feedback requirement complete until an owner submits relevant
feedback and records its actual receipt.
