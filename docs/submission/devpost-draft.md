# Devpost draft — not submitted

Owner must review against the actual Devpost fields and official track rules.
No existing external draft, eligibility, deadline, feedback receipt or judge access
was available. Replace pending fields only with verified links. This text makes
no native Alexa+, Polly, AgentCore or production-readiness claim.

## Project name and tagline

**AfterWard — A living recovery plan for Simulated Alexa+**

**From discharge paperwork to the next clear step at home.**

## Inspiration

Leaving hospital often means following a complicated set of instructions without
the structure of the ward. We wanted a companion that makes the patient's own
letter easier to use: what matters today, what has been completed, and where an
answer came from.

## What it does

AfterWard is a synthetic-data prototype. It turns a discharge letter into a
structured recovery plan, presents daily activities and medicines, supports
rule-based check-ins, records reported task/medicine completion through MCP, and
shows letter evidence alongside answers. In the demonstrated blood-thinner case,
the letter does not give an end date, so the answer asks for confirmation instead
of supplying one.

The interface is explicitly **Simulated Alexa+**. Speech synthesis and optional
recognition use browser APIs. Native Alexa+ device integration has not been
verified. This is not a validated clinical service.

## How we built it

The document flow uses S3, SQS, Lambda, Bedrock, DynamoDB and S3 Vectors. The
`discharge-letter-check` v0.1.0 package supplies extraction schema, instruction
types and validation helpers; AfterWard implements the AWS orchestration,
application recovery state, retrieval, agent behavior and reminder experience.

The browser calls a server-side bridge, and the agent uses authenticated MCP
tools. The verified cloud MCP service runs on ECS Fargate behind ALB/CloudFront;
the active application path has not been established as using AgentCore or Polly.
The local app registers seven MCP tools. The cloud endpoint tested on 17 October
listed six, without undo_report. The hosted frontend and full end-to-end public
journey remain unverified; bridge/Amplify deployment files are preparations.

## What we learned and what is working

MCP provides a clear boundary between conversation, evidence retrieval and state
changes. Page-preserving retrieval makes the letter inspectable. Explicit unknowns
matter: “continue as directed” does not justify an invented stop date.

In the current review, 841 default Python tests and 73 web tests passed. Ten live
AWS integrations were excluded. A separate final-model evaluation using the
configured Sonnet 4.5 profile and synthetic in-memory tools passed 13 of 14 checks;
three crisis probes made zero model/tool calls. The failed check was an ambiguous
medicine report that the current deterministic policy recorded without naming
confirmation. That remains a workflow risk, not a successful safety result.

## Challenges and next steps

Visitors currently share a demo patient, and conversation/crisis state is held
per process. Before an unrestricted public demo or patient use, we need isolation,
shared session state, a reviewed medication-confirmation workflow, isolated PDF
processing, deployed abuse-control verification and clinical evaluation. Browser
voice behavior also varies by platform. The prototype does not replace the care
team or establish clinical benefit.

## Built with

Python, TypeScript, Next.js, browser Web Speech APIs, MCP, discharge-letter-check,
Amazon Bedrock, S3, SQS, Lambda, DynamoDB, S3 Vectors, ECS/Fargate, ECR, ALB,
CloudFront, Secrets Manager, EventBridge Scheduler and CloudWatch. Service roles
are code/configuration evidence; consult the readiness review for what was tested
live. Amplify is deployment preparation, not a verified hosted frontend.

## Links and required evidence — pending owner verification

| Field | Current state |
| --- | --- |
| Source repository | Git origin: https://github.com/charvimaurya/AfterWard-A-Living-Recovery-Plan-for-Alexa — judge access/visibility and release snapshot unverified |
| Demo video | **MISSING** — record/export/review the three-minute script |
| Interactive demo | **CANNOT VERIFY** — no frontend URL supplied; do not use the MCP endpoint as the app link |
| Package | https://github.com/charvimaurya/discharge-letter-check — local installed integration verified; anonymous link access not verified here |
| Product feedback | **MISSING EVIDENCE** — see checklist; no feedback sent or claimed |
| Official hackathon and track | **CANNOT VERIFY** — official URL/rules and 15 October guide required |
| Existing Devpost page / team / submission status | **CANNOT VERIFY** — no URL, team or submission receipt supplied |

Before posting, reconcile the narrative with the actual recorded target and replace
or remove pending links according to the event's requirements. Do not omit known
limitations or add capabilities that only exist in plans.
