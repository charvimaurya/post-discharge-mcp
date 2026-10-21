# Devpost product feedback: five answers to paste

Every point comes from our build. Details and dates are in our public friction log:
https://github.com/charvimaurya/post-discharge-mcp/blob/main/docs/friction-log.md

---

## Q1. Which developer tools, APIs and SDKs did you use, and for what?

1. Alexa Skills Kit, Alexa Developer Console and ASK SDK for Python (ask-sdk-core): a classic Alexa custom skill ("open after ward"), tested in the console simulator, that uses the same bridge and MCP tools as our web client. We also read the Alexa+ documentation (Category SDK, MCP Toolkit); the toolkit is open only to selected partners, so Alexa+ itself is simulated in a web app and clearly labelled.

2. MCP Python SDK, MCP Apps, MCP Inspector and MCPJam: our self-hosted MCP server over Streamable HTTP, on spec 2025-11-25, with 9 tools (6 read, 3 write), 2 prompts (ask_my_letter, morning_checkin) and an MCP App Today card. Inspector and MCPJam were used to test tools, prompts and the App card.

3. Amazon Bedrock (Converse API): Claude Sonnet 4.5 (Haiku 4.5 for testing) reads each discharge letter into a fixed form using forced tool output, and runs the assistant that chooses MCP tools. Amazon Titan Text Embeddings V2 turns letter passages and questions into vectors.

4. Amazon S3 Vectors: stores each page of the letter, so answers quote the exact sentence and page number, filtered to one patient and one letter.

5. Amazon S3, Amazon SQS (with a dead-letter queue) and AWS Lambda, through Boto3: the letter pipeline. Upload to S3, a message on SQS, then a Lambda worker that calls Bedrock, runs our open-source safety gate (discharge-letter-check) and saves the plan.

6. Amazon DynamoDB: two tables, one for the recovery plan and waiting reminder, and one for the history of tasks done and doses taken (with undo).

7. Amazon EventBridge Scheduler: runs our reminder Lambda every 5 minutes, so AfterWard can speak first before something is due.

8. Amazon ECS on Fargate, Amazon ECR, Elastic Load Balancing, Amazon CloudFront and AWS Secrets Manager: host the MCP server container over HTTPS, with the bearer token kept in Secrets Manager.

9. Amazon CloudWatch, AWS CloudFormation and AWS IAM: JSON logs with no patient data, five metrics, three alarms with email alerts (deployed from one stack), and a separate role for each Lambda, the scheduler and the ECS task.

10. Amazon Bedrock AgentCore: tried for hosting the MCP server; not used in the final app (see Q3).

11. Supporting tools: Python with Starlette and uvicorn (bridge and MCP server), Next.js and TypeScript (simulated Alexa+ client), the browser's Web Speech API (voice in and out for the simulation), Docker (MCP server image), a Cloudflare quick tunnel (to reach the local bridge from the Alexa simulator), and GitHub with GitHub Actions (CI for our open-source package on Python 3.11 to 3.13).

---

## Q2. For each tool, API or SDK, what worked well?

1. Alexa Skills Kit and ASK SDK for Python: the SDK's request signature and timestamp checks made securing our endpoint easy, and the simulator let us check the recognised intent and slot value for each phrase.

2. MCP Python SDK and MCP Apps: Streamable HTTP worked through a load balancer and CloudFront once configured. One server now serves our web client, our Alexa skill and MCP Apps hosts. The Today card rendered in MCPJam Chat with no app changes. Putting the safety rules inside the tools meant every client got them for free.

3. Amazon Bedrock: forced tool output gave dependable JSON for extraction. EU inference profiles kept requests in the EU. One setting (MODEL_MODE) switches between Haiku for testing and Sonnet for final runs. CloudWatch showed the tokens each letter used (about 7,400 in, 2,700 out).

4. Amazon S3 Vectors: serverless and low cost. The patient filter returned the right passage of the right letter, with its page number, so every answer can show its evidence.

5. S3, SQS and Lambda: a PDF became a ready plan in about 15 seconds, with a clear log line per stage. The dead-letter queue stopped a bad letter from looping forever.

6. Amazon DynamoDB: simple and reliable for one small item per medicine, task and day. Every MCP tool reads or writes through it.

7. Amazon EventBridge Scheduler: ran the reminder check every 5 minutes with 0 errors over the 3 hours we checked on 18 October.

8. ECS on Fargate with ECR, ELB, CloudFront and Secrets Manager: the MCP server ran without a restart from 13 October; a redeploy on 20 October picked up 9 tools and 2 prompts. The token never appears in code or task settings.

9. CloudWatch and CloudFormation: one stack created all three alarms with email alerts, and the logs made each pipeline stage easy to follow.

10. Supporting tools: Python made it easy to pin every safety rule with tests (1,269 passing). Next.js let us build large, simple cards for older users quickly. GitHub Actions gave our open-source package a public green badge on three Python versions.

---

## Q3. For each tool, API or SDK, what needs work?

1. Alexa+ (Category SDK, MCP Toolkit), Critical: the toolkit is open only to selected partners, so a working MCP server cannot be tried on real Alexa+. We also found no documented way for an add-on to speak first, which is the heart of a recovery companion. Ask: open the toolkit (or a sandbox) to hackathon teams, and document permission-based proactive speech.

2. Amazon Bedrock tool use, Important (safety): the model sometimes said "your letter doesn't mention driving" without calling our search tool; the letter does mention it. We added code checks and a second model call. Ask: a documented "answer only after retrieval" pattern or grounding check.

3. Amazon Bedrock structured extraction, Important (safety): extraction silently dropped the letter's emergency phone number because no field held it. Ask: return the source lines that were not mapped to any field. Wording also varies between runs, with no deterministic mode for tests and demos.

4. Alexa Skills Kit, Important: (a) Alexa waits about 8 seconds; one reply took 9 and failed, so a progressive "one moment" response by default would help. (b) Python handlers are sync only, so calling our async agent timed out until we used a worker thread. (c) Requests do not say which sample phrase matched. (d) A classic skill cannot speak first. (e) A pasted but unsaved endpoint shows only as "skill did not provide a valid response".

5. MCP Python SDK, Important: (a) its DNS-rebinding check rejected requests through the load balancer and CloudFront until we added both host names; this is not documented for AWS hosting. (b) When our MCP server was not running, the client raised an ExceptionGroup with the real ConnectError hidden inside; a clear "cannot connect to <url>" error would save time. (c) How long an MCP App instance lasts across several tools is not documented, and the MCPJam Tools pane shows JSON rather than the App.

6. Amazon S3 Vectors, Important: a query against an index with no matching vectors returns empty results with no warning; a settings mismatch cost us about 2 hours. Encryption is fixed when the vector bucket is created, and the console cannot show stored passages.

7. Amazon ECS on Fargate, IAM and CloudFormation, Important: a new task definition had no log configuration, so errors were invisible, and an IAM simulation showed the execution role could not write logs (fixed by our admin and deployed 18 October). Ask: logging on by default, or a deploy-time warning. The console shows health "UNKNOWN" when no health check is set.

8. S3, SQS and Lambda, Nice-to-have: buckets, queues and functions cannot be renamed, so renaming the project meant recreating everything (about 3 hours). Python dependencies for Lambda needed a hand-built zip.

9. Amazon Bedrock AgentCore, Important: three deploys of the starter project in six minutes all stopped with "No resources defined in project", so we moved to ECS.

10. CloudWatch alarms, Nice-to-have: an alarm that fired before its email subscription was confirmed never sent a message, because alarms notify only when they enter ALARM.

11. Browser Web Speech API (our Alexa+ stand-in), Important (safety): "I fell in the bathroom" was heard as "I feel in the bathroom", so a fall was missed until we added code for likely mishearings. Recognition alternatives and confidence for short phrases would help, on Alexa+ too.

---

## Q4. How was your onboarding experience? (zero to hello world)

This was our first build on AWS and our first voice agent.

1. Alexa Skills Kit: quick to a first response in the simulator. The surprises were that the invocation name had to be two words ("after ward"), the sync-only Python handlers, and the tunnel endpoint needing to be re-saved after every restart. Alexa+ itself: blocked, as the toolkit is not open to us.

2. MCP Python SDK: a first tool was quick. Production hosting behind AWS proxies took about 2 hours, mostly the undocumented Host header check. MCP Inspector and MCPJam made testing tools, prompts and the App card easy.

3. Amazon Bedrock: model access and the Converse API were straightforward. The real work was keeping answers grounded in the letter, not the setup.

4. Amazon S3 Vectors: simple setup. The silent empty result was the only blocker.

5. S3, SQS, Lambda and Boto3: the core pipeline was straightforward. About a day went on permissions fixed one link at a time and packaging Python dependencies, which we solved with a build script.

6. Amazon DynamoDB: quick to set up once we chose one item per medicine, task and day.

7. Amazon EventBridge Scheduler: the easiest service we used; one schedule and one invoke policy.

8. ECS on Fargate, ECR, ELB and CloudFront: harder. We came here after AgentCore would not deploy, and logging was not on by default.

9. CloudWatch, CloudFormation and IAM: our IAM user could not use CloudFormation, so an admin had to deploy the alarm stack. Once deployed, it just worked.

10. Amazon Bedrock AgentCore: we could not get past the first deploy of the starter project.

Overall: each service was quick to get working on its own. The hard part was joining them into one reliable, safe system, and doing it for the first time on AWS.

---

## Q5. Would you build with these devices and services again?

Yes.

- Amazon Bedrock: forced tool output made extraction from discharge letters dependable, and it let us keep AI for understanding while plain code decides anything about medicines, times and emergencies.
- MCP: putting every safety rule inside the tools meant our web client, our Alexa skill and MCP Apps hosts all behave the same. It is the right shape for Alexa+.
- S3, SQS, Lambda, DynamoDB, S3 Vectors and EventBridge: a serverless pipeline that turned a PDF into a plan in about 15 seconds, at low cost, with failures caught by a dead-letter queue and alarms.
- ECS on Fargate: the right home for a long-running MCP endpoint.
- Alexa: yes, and we would be first in line for the Alexa+ MCP Toolkit. A patient whose hands are on a walking frame needs voice, and AfterWard's MCP server is ready for it today.

The one exception is Bedrock AgentCore: not yet. We would try it again once the starter project deploys out of the box.

Next time we would turn on logging and permission checks on day one, and test the full chain (schedule to spoken reminder) early.
