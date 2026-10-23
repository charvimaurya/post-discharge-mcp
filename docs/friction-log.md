# AfterWard friction log

Built 31 Aug to 23 Oct 2026. Team: Charvi Maurya (developer), Shilpa Agarwal (mentor).
First time using AWS and first time building a voice agent.
Repository: public, at https://github.com/charvimaurya/post-discharge-mcp.

These are the 15 issues that mattered most, **ordered by impact**: patient safety first, then
what shaped the product and the AWS build. Every one was found by building and testing the
working app with synthetic discharge letters. Each entry gives the six things Amazon asked for:
task attempted, steps taken, expected vs. actual result, severity, workaround and an actionable
suggestion. Where an entry says "fixed", the fix has automated tests (1,298 Python tests passing
on 21 Oct 2026). Time lost is approximate; most times were estimated by the team afterwards.

**Severity:** High = blocked a core feature or created a patient-safety risk. Medium = cost real
time or forced a design change. Low = an annoyance with a quick workaround.

## Summary

| # | Date | Product / service | Issue | Severity | Time lost | Status |
|---|---|---|---|---|---|---|
| 1 | Oct | Alexa+ (Category SDK, MCP Toolkit) | Toolkit open only to selected partners | High | ~3 h | Simulated Alexa+ |
| 2 | 15 Oct | Amazon Bedrock (Converse tool use) | Said "not in your letter" without searching | High | ~2 h | Fixed in code |
| 3 | 15 Oct | Amazon Bedrock (structured extraction) | Emergency phone number silently dropped | High | ~1.5 h | Fixed in code |
| 4 | 15, 17 Oct | Browser speech recognition (stand-in for Alexa+) | "I fell" heard as "I feel": a fall was missed | High | ~2.5 h | Fixed in code |
| 5 | 13 Oct | Amazon S3 Vectors | Wrong index returned empty results, no error | High | ~2 h | Fixed in config |
| 6 | 16 Oct | Alexa custom skill + Amazon Bedrock | 9 s reply passed Alexa's ~8 s limit | High | ~2 h | Fixed in code |
| 7 | 17 Oct | Alexa custom skill (classic) | A classic skill cannot speak first | Medium | ~1.5 h | Simulated on web |
| 8 | 4 to 5 Oct | Amazon Bedrock AgentCore | Starter project would not deploy | Medium | ~1 h | Moved to ECS |
| 9 | Oct | MCP Python SDK + ELB + CloudFront | Host header check rejected proxied requests | Medium | ~2 h | Fixed in config |
| 10 | 15 to 18 Oct | Amazon ECS on Fargate, IAM, CloudFormation | Task had no logging; role could not write logs | Medium | ~0.5 h | Fixed, deployed 18 Oct |
| 11 | 14 Oct | Amazon S3, SQS, Lambda, IAM | Resources cannot be renamed | Medium | ~3 h | Scripted migration |
| 12 | 14 Oct | AWS Lambda (Python packaging) | Dependencies zipped by hand | Medium | ~1.5 h | Build script |
| 13 | 16 Oct | Alexa Skills Kit SDK for Python | Sync-only handlers; matched sample not reported | Medium | ~2 h | Fixed in code |
| 14 | 18 Oct | MCP Python SDK (Streamable HTTP client) | Connection failure hidden in an ExceptionGroup | Medium | ~1 h | Diagnostics added |
| 15 | 16 to 18 Oct | Alexa endpoint + Cloudflare quick tunnel | Unsaved endpoint looks like "invalid response" | Low | ~1 h | Start script helps |

## Top 3 suggestions

1. **Alexa+:** open the MCP Toolkit to hackathon teams, or provide a sandbox. Our MCP server
   already works; Alexa+ itself is the only part we had to simulate, and browser speech
   recognition is the weakest part of the voice experience, especially for the short answers
   older patients give (entry 4).
2. **Amazon Bedrock tool use:** make "answer only after retrieval" easy to enforce, so a health
   assistant can never say "your letter doesn't say" without having looked (entry 2).
3. **Amazon Bedrock extraction:** report the text a structured extraction did not map to any
   field. In a discharge letter, a dropped phone number is a safety gap, not a formatting
   issue (entry 3).

---

## Entries

### 1. Alexa+ (Category SDK, MCP Toolkit): no access for hackathon teams

- **Task attempted:** Ship AfterWard as a real Alexa+ experience, using our self-hosted MCP server.
- **Steps taken:** Read the Alexa+ developer documentation for the Category SDK and MCP Toolkit,
  then looked for an access request route on the hackathon resources page.
- **Expected:** A way to connect our working MCP server to Alexa+.
- **Actual:** The documentation says both are available only to selected partners, and no access
  form was listed, so we could not deploy to Alexa+.
- **Severity:** High (~3 h)
- **Workaround:** Built a simulated Alexa+ in the browser (speech in, speech out, the same MCP
  tools), clearly labelled as simulated, plus a classic Alexa custom skill on the same tools.
- **Suggestion:** Open the MCP Toolkit to hackathon teams, or provide a sandbox, so a working MCP
  server can be tried on real Alexa+.

### 2. Amazon Bedrock (Claude Haiku 4.5, Converse API with tool use): "not in your letter" without looking

- **Task attempted:** Answer "Can I go for a drive?" only from the patient's own letter.
- **Steps taken:** Asked the question through the Converse API with our letter-search tool
  available, then compared the answer with the letter text.
- **Expected:** The model calls the search tool, then answers from the letter.
- **Actual:** It sometimes replied "I don't have information about driving in your recovery plan"
  **without calling the search tool**. The letter says "Do not drive until your consultant has
  reviewed you". A wrong "not in your letter" is a safety risk.
- **Severity:** High (~2 h)
- **Workaround (fixed):** Code checks every reply. A question about whether something is allowed,
  or any "not in your letter" answer, must follow a letter search; otherwise the model is sent
  back to search first.
- **Suggestion:** A documented "answer only after retrieval" pattern for Converse tool use, or a
  grounding check that flags "not found" claims made without a retrieval call.

### 3. Amazon Bedrock (structured extraction from the PDF): emergency number silently dropped

- **Task attempted:** Turn the discharge letter into a plan, including who to call in an emergency.
- **Steps taken:** Ran structured extraction on the synthetic letter with our schema, then checked
  the emergency instruction in the saved plan.
- **Expected:** Both emergency lines kept.
- **Actual:** Extraction kept "Call emergency services straight away" but **silently dropped the
  next line, "Emergency services number: 555-555-0199"**, because no field in our schema held it.
  The app fell back to saying 999.
- **Severity:** High (~1.5 h)
- **Workaround (fixed):** At answer time AfterWard looks the number up in the patient's own letter
  (S3 Vectors) and uses it in the spoken reply, the help banner and the evidence panel; 999 is
  used only when the letter gives no number.
- **Suggestion:** Report the letter lines a structured extraction did not map to any field, so
  safety-relevant text (phone numbers, contacts) is never lost silently.

### 4. Browser speech recognition (Web Speech API in Chrome, standing in for Alexa+): a fall was missed

- **Task attempted:** Let an older patient speak naturally, including reporting a fall.
- **Steps taken:** Spoke test phrases into the simulated Alexa+ client and checked the transcripts
  the browser returned.
- **Expected:** Short phrases transcribed accurately.
- **Actual:** "can I" became **"can a"** and "both" became "boat". Worse, **"I fell in the
  bathroom" was heard as "I feel in the bathroom"**, so the safety code missed a fall and the AI
  said "call 999" instead of the letter's number.
- **Severity:** High (~2.5 h)
- **Workaround (fixed):** Misheard forms accepted where the meaning is clear; "I feel in the / on
  the floor / down the stairs" treated as a likely fall; AI replies about symptoms use the letter's
  number; tap-to-answer buttons for short answers.
- **Suggestion:** Expose recognition alternatives and confidence for short utterances, so apps can
  check "fell" against "feel". The same matters for Alexa+.

### 5. Amazon S3 Vectors: empty results with no warning

- **Task attempted:** Search the patient's letter for the passage behind each answer.
- **Steps taken:** Switched the document Lambda to a new vector bucket and index, then ran letter
  searches from the local app.
- **Expected:** Matching passages with page numbers.
- **Actual:** Local settings still named the old index. **Every letter search returned
  "insufficient evidence" with no error**, so the evidence panel never opened.
- **Severity:** High (~2 h)
- **Workaround (fixed):** Pointed `S3_VECTOR_BUCKET` and `S3_VECTOR_INDEX` at the same index as the
  Lambda, and now check the Lambda's settings whenever search goes empty.
- **Suggestion:** A clear error, or a warning in the response, when a query runs against an index
  that holds no vectors for that filter.

### 6. Alexa custom skill (response time) with Amazon Bedrock: reply too slow

- **Task attempted:** Answer "I've taken both. How long do I take them for?" on Alexa.
- **Steps taken:** Asked the question in the Alexa developer console simulator and timed the reply.
- **Expected:** A reply within Alexa's time limit.
- **Actual:** The reply took 9.0 s; Alexa waits about 8 s, so the skill failed.
- **Severity:** High (~2 h)
- **Workaround (fixed):** "How long" questions about just-reported medicines are answered in code
  from the letter; now about 3 s.
- **Suggestion:** Let a skill send a progressive "one moment" response by default when it nears
  the limit.

### 7. Alexa custom skill (classic): cannot speak first

- **Task attempted:** Have AfterWard speak first with the morning reminder.
- **Steps taken:** Checked what a classic skill can do without the user speaking first.
- **Expected:** A way for the skill to start the conversation.
- **Actual:** A classic skill can only reply when the user speaks first. Proactive speech needs
  Amazon's reminder or notification features, user permission and usually certification.
- **Severity:** Medium (~1.5 h)
- **Workaround:** "Speaks first" runs on the web companion, labelled as simulated, using the same
  reminder rules that EventBridge Scheduler runs on AWS every 5 minutes; Alexa is used where the
  patient speaks first.
- **Suggestion:** A sandbox for proactive reminders in development skills, and a documented way
  for Alexa+ add-ons to speak first.

### 8. Amazon Bedrock AgentCore (starter project, `agentcore deploy`): would not deploy

- **Task attempted:** Host the MCP server on AgentCore.
- **Steps taken:** Ran `agentcore deploy` on the starter project three times in six minutes.
- **Expected:** The starter project deploys.
- **Actual:** Every run stopped at the first check: **"No resources defined in project. Add at
  least one resource (agent, memory, knowledge base, evaluator, or gateway) before deploying."**
- **Severity:** Medium (~1 h)
- **Workaround:** Moved the MCP server to a container on ECS Fargate behind a load balancer and
  CloudFront, and removed the starter project.
- **Suggestion:** A starter that deploys out of the box, or one that shows how to add the first
  resource before deploy is run.

### 9. MCP Python SDK with Elastic Load Balancing and CloudFront: Host header rejected

- **Task attempted:** Reach the MCP server on ECS through the load balancer and CloudFront.
- **Steps taken:** Deployed the container, then called `/mcp` through the load balancer and
  through CloudFront.
- **Expected:** Requests reach the server.
- **Actual:** The MCP SDK's DNS-rebinding protection only accepts Host headers on its allowed list.
  The load balancer forwards its own DNS name and CloudFront forwards the CloudFront domain, so
  requests through them were rejected until both names were added. This is the SDK's safety check
  meeting how AWS proxies pass the Host header, not a fault in one product.
- **Severity:** Medium (~2 h)
- **Workaround (fixed):** `ALB_HOST` and `HTTPS_HOST` settings add both names to the allowed hosts
  (`app/mcp/http_server.py`).
- **Suggestion:** A note in AWS guidance for hosting MCP servers on ECS: which Host header the load
  balancer and CloudFront send, and that the MCP Host check must allow it.

### 10. Amazon ECS on Fargate, IAM and CloudFormation: no logs reached CloudWatch

- **Task attempted:** Turn on CloudWatch logging and alarms for the MCP server and failed letters.
- **Steps taken:** Added `awslogs` settings to the task definition, wrote the alarm template and
  validated it offline, then ran a read-only IAM policy simulation for the task execution role.
- **Expected:** The server's errors reach CloudWatch, so a tool-error alarm can fire.
- **Actual:** The running task had **no log configuration**, so its errors never reached
  CloudWatch. On 17 Oct the IAM simulation returned `implicitDeny` for `logs:CreateLogStream` and
  `logs:PutLogEvents` on the execution role. Our IAM user also could not use CloudFormation, so
  the alarm template needed an admin.
- **Severity:** Medium (~0.5 h, plus an admin dependency)
- **Workaround (fixed):** Prepared a scoped policy and steps for the admin. On 18 Oct the admin
  granted it, created the log group, switched the task to CloudWatch logging and deployed the
  alarm stack. Three alarms are now live with email alerts.
- **Suggestion:** Turn on CloudWatch logging by default for new Fargate task definitions, or warn
  at deploy time when a service has no logging or its execution role cannot write the log group.

### 11. Amazon S3, SQS, Lambda (resource names) and IAM: nothing can be renamed

- **Task attempted:** Rename the project from CareLoop to AfterWard.
- **Steps taken:** Took an inventory of the AWS resources, then tried to rename them and create the
  new ones.
- **Expected:** Rename resources in place.
- **Actual:** S3 buckets, SQS queues and Lambda functions cannot be renamed, so every resource had
  to be recreated and the letters copied across. Our IAM user also lacked permissions the
  migration needed (`implicitDeny` for `s3:CreateBucket`; access denied for `ecs:ListServices`
  and `sqs:ListQueueTags`).
- **Severity:** Medium (~3 h)
- **Workaround:** Scripted migration (inventory, copy, verify); old CareLoop resources kept for
  rollback. A scoped managed policy allowed creating the new bucket without granting any delete
  permission.
- **Suggestion:** A rename or "move" for buckets, queues and functions, or a guided migration that
  lists the IAM permissions it needs before it starts.

### 12. AWS Lambda (Python packaging): dependencies zipped by hand

- **Task attempted:** Deploy a fix to the document-processing Lambda.
- **Steps taken:** Bundled the Python dependencies into a local zip and uploaded it by hand,
  keeping the previous code as version 1 for rollback.
- **Expected:** A simple, repeatable way to ship Python dependencies.
- **Actual:** Each deploy needed a hand-built zip with the right x86_64 wheels.
- **Severity:** Medium (~1.5 h)
- **Workaround:** A build script that packages the Lambda the same way every time.
- **Suggestion:** A simpler path to package Python dependencies for Lambda without containers or
  manual zips.

### 13. Alexa Skills Kit SDK for Python (`ask-sdk-core`) and interaction model: sync handlers, no matched sample

- **Task attempted:** Pass the patient's exact words, such as "I just came back from my walk",
  from the skill to our async agent.
- **Steps taken:** Built handlers with `ask-sdk-core`, called our async agent from them, then tested
  completion phrases in the simulator and checked the recognised intent and query.
- **Expected:** The full sentence reaches the agent quickly.
- **Actual:** ask-sdk handlers are sync and our agent is async, so the first test timed out. Alexa
  also reports only the intent and slot, not which sample matched, so one fixed opening garbled
  sentences ("I've taken my breakfast…").
- **Severity:** Medium (~2 h)
- **Workaround (fixed):** Handlers run in a worker thread and hand the turn to the bridge's event
  loop. One intent per opening phrase (`CameBackFromIntent`, `FinishedIntent`, `CompletedIntent`),
  all sharing one handler.
- **Suggestion:** An async request-handler option in the Python SDK, and the matched sample (or
  carrier phrase) in the request.

### 14. MCP Python SDK (Streamable HTTP client): a simple connection failure was hidden

- **Task attempted:** Open the classic Alexa skill ("open after ward") and have it read today's
  plan through our MCP server.
- **Steps taken:** Started the bridge on port 8002, launched the skill from the Alexa simulator,
  saw `LaunchRequest` return HTTP 200 but the bridge log `alexa_turn_failed` with
  `ExceptionGroup`, reproduced it with a read-only `get_today_tasks` call, then checked which
  ports were listening.
- **Expected:** The skill reads Margaret's tasks.
- **Actual:** Alexa authentication succeeded, but the MCP client raised an `ExceptionGroup` whose
  only useful detail, an HTTP `ConnectError`, was nested inside it. The cause was our own: the MCP
  server was not running on port 8001. The tooling gap is that the error did not say so.
- **Severity:** Medium (~1 h)
- **Workaround (fixed):** Started the MCP server; `get_today_tasks` and `get_medications` each
  returned 7 occurrences. Our logs now record the nested error types (never messages, URLs or
  patient text), with regression tests.
- **Suggestion:** Raise a clear top-level error such as "Cannot connect to MCP server at <url>"
  instead of an `ExceptionGroup`, so the cause is visible without reading a traceback.

### 15. Alexa endpoint with a Cloudflare quick tunnel: unsaved endpoint looks like a broken skill

- **Task attempted:** Reach the local bridge from the Alexa developer console simulator.
- **Steps taken:** Started the MCP server, bridge and a Cloudflare quick tunnel, pasted the
  tunnel's HTTPS address into the skill endpoint, and tested in the simulator after each restart.
- **Expected:** A stable endpoint for testing.
- **Actual:** The endpoint needs the "wildcard certificate" option, and the free tunnel address
  changes on every restart. A new address that is pasted but **not saved** shows only as "skill
  did not provide a valid response", with no request reaching the bridge. On 18 Oct no tunnel
  process was running at all, so the saved endpoint was stale.
- **Severity:** Low (~1 h)
- **Workaround:** The start script copies the new endpoint to the clipboard; paste it and click
  Save Endpoints after every restart, and check the bridge health URL first.
- **Suggestion:** Warn about unsaved endpoint changes before testing, explain the certificate
  options for tunnels, and say "no request reached your endpoint" when that is what happened.

---

## What worked well

- **S3 → SQS → Lambda → Bedrock** turned an uploaded letter into a ready plan in about 15 seconds,
  with a clear log line for every stage (received, extracted, checked, saved, indexed, ready) and
  no patient details in the logs.
- **EventBridge Scheduler** ran the reminder check every five minutes with no errors.
- **ECS on Fargate** kept the MCP server running without a restart since 13 Oct.
- **S3 Vectors** with a patient filter returned the right passage of the right patient's letter,
  with its page number, so every answer can show its evidence.
- **CloudWatch** alarms for tool errors, failed letters and MCP health were deployed from one
  CloudFormation stack on 18 Oct, with email alerts.
- **Safety replies built in code, not by the model:** symptoms are answered only with the letter's
  own warning signs, word for word, so the most important replies are predictable.
- **Open source:** the letter validator became a standalone package,
  [discharge-letter-check](https://github.com/charvimaurya/discharge-letter-check), which
  AfterWard now uses.
- **Automated tests** caught every regression while fixing the items above: each fix added a test
  with the patient's exact words.

## MCP Apps integration

Running an App-linked tool (`get_today_tasks`) in the Tools pane of MCPJam Inspector 3.16.1
returned JSON instead of the card; the pane said the tool renders UI through MCP Apps and to use
Chat. In Chat/Playground the card rendered inside the MCP Apps sandbox, with progress, completed
ticks and the next task. No application change was needed. Registration, resource type, tool
metadata and malformed-input handling are covered by [MCP App tests](../tests/mcp/test_today_app.py).
