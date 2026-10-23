## At a glance

> **Discharge is one moment. Recovery happens every day.**  
> AfterWard turns a hospital discharge letter into a living recovery plan that speaks, reminds patients what is due, remembers recorded progress and flags unclear instructions—such as a missing end date or conflicting dates—for a person to clarify, never a confident guess.

- 🎥 **Demo video:** [ADD LINK] · 📊 **Demo presentation (PDF):** [AfterWard Hackathon Presentation 2026](https://github.com/charvimaurya/post-discharge-mcp/blob/main/docs/submission/AfterWard_Hackathon_Presentation_2026.pdf) · 💻 **Main repo:** [post-discharge-mcp](https://github.com/charvimaurya/post-discharge-mcp) · 🔓 **Open-source safety gate:** [discharge-letter-check](https://github.com/charvimaurya/discharge-letter-check) · 📝 **Friction log:** [Read the friction log](https://github.com/charvimaurya/post-discharge-mcp/blob/main/docs/friction-log.md) · ☁️ **AWS integrations:** [Service-by-service documentation](https://github.com/charvimaurya/post-discharge-mcp/blob/main/docs/aws-integrations.md)
- 🧰 **Self-hosted MCP server** (MCP spec 2025-11-25, Streamable HTTP) on Amazon ECS: **9 tools, 2 prompts and an MCP App**
- ☁️ **Built on AWS:** Bedrock (Claude and Titan Embeddings), S3, S3 Vectors, SQS, Lambda, DynamoDB, EventBridge Scheduler, ECS on Fargate, CloudWatch, Secrets Manager
- 🛡️ **Safety lives in tested code, not prompts:** **1,269 Python and 130+ web tests passing**, and the open-source package’s CI passes on **Python 3.11–3.13**.
- 🧪 **How judges can test:** follow the step-by-step instructions in [How judges can test](#how-judges-can-test) below.
- ⚠️ **Demo scope:** synthetic patient letters and records; **Alexa+ is simulated** in the Next.js client. A classic Alexa skill, tested in the Alexa developer console simulator, is also part of the build. It does not proactively speak first.

## Inspiration
> **7:00 AM on a Friday morning.** Margaret, 68, is recovering at home after knee replacement surgery. Nobody has asked anything, but the screen beside her lights up and speaks:
>
> *"Good morning, Margaret. I hope you slept well. You have about thirty minutes until your morning walk, at half past seven."*

**That moment is why we built AfterWard.**

### The care team stays at the hospital. The paper goes home.

When patients leave the hospital, they take home a few sheets of discharge instructions. From that moment, they and their caregivers must remember which medicines are due, what activities are safe, when follow-up appointments are scheduled, and which warning signs require urgent help.

They must manage all of this while tired, sore, recovering from surgery, or simply overwhelmed.

The information may be written on the page. But **paper cannot notice that you have already completed your morning walk. It cannot remember what you have done, tell you what comes next, or proactively remind you when something is due.**

According to [AHRQ's 2023 Nationwide Readmissions Database](https://hcup-us.ahrq.gov/db/nation/nrd/NRDIntroduction2023.pdf), US hospitals recorded approximately **3.77 million readmissions within 30 days**, representing a **13.5% readmission rate**. Although readmissions have many causes, these figures demonstrate the scale of the challenges surrounding recovery after discharge.

### We wanted to make recovery easier at home.

Our inspiration became Margaret, a 68-year-old synthetic patient recovering from knee replacement surgery.

She has a new knee, a walking frame, medicines to remember, exercises to complete, and follow-up appointments to attend.

Her hands are often occupied with her walking frame, making **speaking easier than navigating a phone or typing instructions**.

We wanted to transform her discharge letter from passive paperwork into an active, personalised recovery companion.

Something that could:

* **Speak first:** Proactively remind her about upcoming recovery activities.
* **Remember her progress:** Track completed walks, exercises, and recorded medicines.
* **Guide her through each day:** Help her understand what comes next.
* **Answer from her own discharge letter:** Provide answers grounded in her actual instructions.
* **Flag uncertainty instead of guessing:** Highlight unclear medical instructions rather than inventing answers.

We called it **AfterWard** because hospital care happens on the ward, but recovery continues long after patients leave it.

Our ambition extends beyond Margaret. We want recovery support to become more accessible to people of different ages, abilities, and backgrounds, wherever they live.

AfterWard is our first step toward that vision: a voice-first recovery companion demonstrated through a **simulated Alexa+ experience**, using entirely synthetic patient data.

🔴 **Our mission: no one should have to remember their recovery alone.**

*Discharge is one moment. Recovery happens every day.*

## Why AfterWard, when Alexa+ already exists?

Alexa+ can help with reminders and questions. **AfterWard adds the recovery-specific layer that joins those capabilities into one persistent plan built from the patient's discharge letter.**

> **A reminder knows when. AfterWard knows what the letter says, what has been recorded as done, and what is still next.**

That difference matters. **A generic reminder does not know that Margaret finished her morning walk;** a document Q&A tool does not maintain a day-by-day record of medicines and exercises. AfterWard connects both through an MCP server, patient-scoped recovery state and source-linked instructions. If the letter is ambiguous, deterministic checks preserve the uncertainty rather than guessing.

This MVP was built for the hackathon demo using a simulated Alexa+ client and synthetic patient data. It demonstrates the experience we want to build.

## What it does

AfterWard is a **voice-first post-discharge companion designed for an Alexa+ experience**. Upload a discharge letter once, and it becomes a living plan for medicines, activities and follow-ups. In this hackathon build, a **simulated Alexa+ web client** delivers proactive spoken reminders; a separate classic Alexa skill can respond when invoked.

- 📄 **It builds the plan for you.** Medicines, walks, exercises, appointments, restrictions and warning signs, each one keeping the exact sentence it came from. Nobody types anything in.
- 🔔 **It speaks first in the demo.** Before something is due, the simulated client speaks a reminder without waiting for a question.
- ✅ **It remembers what you have done.** *"I'm back from my walk."* → *"Well done, Margaret, that's your morning walk done. Next is your paracetamol and blood thinner, after breakfast."*
- 📖 **It answers from her own letter.** *"What does my letter say about driving?"* AfterWard quotes the instruction and highlights the sentence on screen, with the page number.
- 🛑 **It never guesses.** Her blood thinner has no end date in the letter. AfterWard says so, won't invent one, and tells her to ask her care team.
- 🚨 **It takes warning signs seriously.** *"My calf is swollen and I'm a bit short of breath."* → fixed crisis and warning-sign handling routes the response without relying on generative improvisation. It is not a medical triage service.
- 📊 **It shows the recorded week.** The seven-day view separates completed recovery tasks from morning-medicine confirmations. A day-details tool can retrieve medication and activity records for a selected date. Missing history stays **unknown**, not automatically **missed**; historical medication confirmation requires matching schedule evidence. A dedicated full-page clickable dashboard with richer daily details is a proposed enhancement, not a claim of completed UI functionality.

| An ordinary reminder or chatbot | AfterWard |
|---|---|
| Waits to be asked | **Simulated client speaks first**, before something is due |
| You type the reminders in | **Builds the plan** from the discharge letter |
| Forgets what you did | **Remembers** what is done and what is next |
| Fills gaps with a confident guess | **Says "I won't guess"** and points to the care team |
| Answers from the internet | **Quotes your own letter**, and shows the sentence |

### One letter. One recovery plan. Every day.

On Friday morning, Margaret hears that her walk is due. She completes it and tells AfterWard, and her recorded plan updates. After breakfast, she reports her medicine. Later, when she asks about driving, the reply is grounded in her own discharge letter, not a generic internet answer. She can also look back at her recorded week and see which activity and morning-medicine events have evidence behind them. **She sees what is known, what was recorded, and what still needs clarification.**

This is a walkthrough of the synthetic demo scenario; it is not a claim that a real patient has used AfterWard.

It is **voice first**, because a patient's hands may be on a walking frame, but **not voice only**: large cards show what is next, and the simulated client also supports text and touch.

*The Alexa+ experience is simulated in a web app, as the hackathon rules allow, and labelled "Simulated Alexa+" on every screen. All patient data is synthetic.*

## How we built it

Our design rule: **AI where understanding is needed, fixed rules where safety matters.**

**1. A letter becomes a plan**

- The letter is uploaded to **Amazon S3**, which sends an event to **Amazon SQS**. An **AWS Lambda** worker picks it up, with a dead-letter queue and an **Amazon CloudWatch** alarm for anything that keeps failing.
- **Claude on Amazon Bedrock** reads the letter into a structured plan using structured output.
- Every item then passes our **open-source safety gate**, `discharge-letter-check`. Fixed rules, not a second model, check every field. An unclear dose is held for confirmation; a missing detail is never invented. A missing end date keeps today's doses but marks the end date as "not stated". Unclear is flagged, **never guessed**.
- The plan is saved in **Amazon DynamoDB**, and the letter is chunked and indexed in **Amazon S3 Vectors** with Titan Text Embeddings V2, filtered to one patient.
- Processing is designed to be **idempotent**: duplicate events do not create duplicate recovery completions. Duplicate-handling safeguards limit unnecessary reprocessing; they do **not** guarantee that every duplicate cloud invocation is free of cost.

**2. Talking to the plan, through MCP**

- A self-hosted **MCP server** (Python MCP SDK, Streamable HTTP, spec 2025-11-25) runs on **Amazon ECS on Fargate**, stateless and scoped to one patient per call.
- 🔧 **9 secure tools**, each with one job, behind bearer-token auth. "Today" is decided by the server, not the AI. Writes are safe to repeat. Every tool returns a clear error with a next step.
  - Read: `get_today_tasks`, `get_medications`, `get_recovery_plan`, `get_week_summary`, `get_recovery_day_details`, `search_discharge_instructions`
  - Write: `report_task_completed`, `report_medication_taken`, `undo_report`
- 💬 **2 MCP prompts** that carry our safety rules to any agent. `ask_my_letter` makes the agent search the letter first and answer only with the page number. `morning_checkin` gives one short spoken step: what is done and what is next.
- 🪟 **An MCP App:** Margaret's Today card. Apps that support MCP Apps (such as MCPJam) draw her progress, her next step and any "needs confirmation" tag, instead of plain text. **One MCP server, many front ends.**
- **Claude on Bedrock** picks the tools for open questions, such as driving rules or how long to take a medicine.
- Moments that touch **medicines, times or emergencies** (reminders, "I'm back", "what's next", warning signs) are answered by **tested code** that still reads and writes through the MCP tools. These replies are the same every time and covered by exact-wording tests.

**3. Speaking first**

- **Amazon EventBridge Scheduler** wakes a reminder Lambda every 5 minutes. It finds anything due within the next 30 minutes, skips "only if needed" medicines and anything unclear, and saves one pending reminder that the client speaks.

**4. The client**

- A **Next.js** simulated Alexa+ client: large text, one next step at a time, and the source sentence on every card.
- A **Developer view** shows every MCP tool call live, so judges can see that each reply comes from a real tool call.
- A **classic Alexa custom skill** that uses the same plan. It is tested in the Alexa developer console simulator and is not published. (A classic skill can't speak first, so reminders stay in the simulated client.)

**5. Built to scale**

If every US hospital admission used AfterWard (35.7 million a year, 30 days of use, 15 tool calls a day, a peak of 10× the average):

$$
\text{peak tool calls} \approx \frac{35.7 \times 10^{6} \times 30 \times 15}{31{,}536{,}000\ \text{s}} \times 10 \approx 5{,}000 \text{ per second}
$$

and about **10 letter uploads a second** at peak. Stateless MCP server copies behind a load balancer, queue-driven workers capped to the Bedrock limit so costs stay bounded, and one small DynamoDB item per medicine, task and day keep this within reach. *These are design figures from stated assumptions, not measurements.*

## Safety and guardrails

AfterWard talks to patients about medicines, so it must never guess. Our safety rules are ordinary, tested Python code, not prompt-only instructions, so they behave the same way every time.

**🩺 No medical advice, ever.** When a patient mentions a symptom (pain, bleeding, dizziness, a fall), the AI is skipped. She hears either her own letter's warning sign, word for word, or a fixed safety line: call emergency services if it is severe or sudden, otherwise her care team.

**📄 Grounded in her letter only.** Every medicine, dose, time and appointment comes from an MCP tool call made in that same request. Answers about her letter carry an evidence tag that links to the exact line used. "Am I allowed to…?" questions must search the letter first.

**✅ Medication-write guardrails, with an identified limitation.** Statements such as "not yet" and "I forgot" block a taken-dose save; AfterWard confirms recording only after the database write succeeds. **When two medicines are due, AfterWard asks which one was taken. When only one is due, it records that medicine and names it**, giving the patient a chance to say "that’s wrong" and undo the entry. **Our final agent evaluation flagged that single-medicine shortcut as too trusting. Always asking for confirmation first is our next fix.** Undo retains the event trail.

**🔒 Patient-scoped demo, not production authentication.** The demo patient is determined by server-side context; the browser or model does not freely choose another patient. Letter searches are filtered by patient, and the AWS design uses encrypted storage and HTTPS. **Production sign-in, consent and patient access management are future work.**

**📈 Observability without patient data.** One request ID follows each message from the browser to the database. Logs keep IDs, counts and timings only: the logger itself drops anything that could be letter text, a medicine name or a patient name, and a test enforces it. Five CloudWatch metrics are built in (chat speed, tool speed, tool errors, blocked writes, upload-to-ready time), with alarms defined as code.

## Challenge tracks and mini challenges

**Alexa+ track — a self-hosted MCP recovery companion.** Our Python MCP server exposes **nine tools, two prompts and an MCP App** over Streamable HTTP (spec 2025-11-25). The Next.js client simulates an Alexa+ interaction; we do **not** claim the simulated client is a released Alexa+ add-on. A classic Alexa skill provides a separate invocation-based entry point.

**AWS Builder — connected services with defined jobs.** S3 receives letters; SQS buffers jobs; Lambda and Claude on Bedrock extract a structured plan; DynamoDB stores recovery state and events; S3 Vectors supports patient-filtered retrieval; EventBridge Scheduler and Lambda handle reminders; ECS Fargate hosts the MCP server; CloudWatch supports observability. See the [AWS integrations documentation](https://github.com/charvimaurya/post-discharge-mcp/blob/main/docs/aws-integrations.md) for the code-level service map and live status.

**Open Source — reusable discharge-letter checks.** We created [discharge-letter-check](https://github.com/charvimaurya/discharge-letter-check), a separate MIT-licensed Python package used by AfterWard to validate structured extraction and flag uncertain fields. **Contribution URL:** [discharge-letter-check v0.1.0](https://github.com/charvimaurya/discharge-letter-check/tree/v0.1.0). **Project repo URL:** [post-discharge-mcp](https://github.com/charvimaurya/post-discharge-mcp). **GitHub username:** `charvimaurya`. **CI:** passes on Python 3.11–3.13. Its value is independent of the demo: other projects can reuse the same deterministic validation layer.

## What we have demonstrated

The evidence here comes from our **synthetic hackathon test environment**, not a clinical trial or a production patient deployment.

| Evidence | Demonstrated in the build | Boundary |
|---|---|---|
| **1,400+ automated tests passing** | **1,269 Python** and **130+ web** tests, from our final test run | Automated coverage is not a guarantee of real-world safety |
| **9 MCP tools + 2 prompts + 1 MCP App** | Read/write recovery plan, search the letter, show Today/week/day history | The MCP App is for compatible hosts; it is not a released Alexa+ add-on |
| **Proactive reminder pipeline** | EventBridge checks every five minutes; the **simulated client** speaks pending reminders | A classic Alexa skill does not proactively initiate this dialogue |
| **Persisted event history** | Recovery tasks and medicine events can be recorded and queried; the weekly view distinguishes task counts from morning-dose evidence | Missing records mean **unknown**, not proof of a missed dose |
| **Reusable open-source validator** | `discharge-letter-check` package; team reports CI passing on Python **3.11–3.13** | Fixed rules cover defined failure modes, not every possible clinical ambiguity |

**An important safety gap is still open:** when only one medicine is due, an ambiguous statement can be recorded without first asking for confirmation. The system names the medicine and supports undo, but our final evaluation classified this as too trusting. We describe this plainly because it is the next behaviour we intend to change, not a solved issue.

## How judges can test

**Watch it work end to end:** [Demo video — ADD LINK]. It shows the live AWS build: a discharge letter becoming a recovery plan, AfterWard speaking first through the simulated Alexa+ client, and answers quoted from the letter.

**Try the MCP server without AWS (about 10 minutes):** [README → Try the MCP server in an MCP client](https://github.com/charvimaurya/post-discharge-mcp#try-the-mcp-server-in-an-mcp-client-without-aws). Explore the **9 tools, 2 prompts and MCP App Today card** with a synthetic patient.

**Try the open-source safety gate:** [discharge-letter-check](https://github.com/charvimaurya/discharge-letter-check). Install it with pip and run its **149 tests**.

**Full setup with your own AWS account:** [README → Run AfterWard locally](https://github.com/charvimaurya/post-discharge-mcp#run-afterward-locally).

For technical evidence, see the [AWS integrations](https://github.com/charvimaurya/post-discharge-mcp/blob/main/docs/aws-integrations.md) and [friction log](https://github.com/charvimaurya/post-discharge-mcp/blob/main/docs/friction-log.md).

**Open Source challenge fields:** GitHub username `charvimaurya` · Contribution: [discharge-letter-check v0.1.0](https://github.com/charvimaurya/discharge-letter-check/tree/v0.1.0) · Main project: [post-discharge-mcp](https://github.com/charvimaurya/post-discharge-mcp).

## Challenges we ran into

- **Our first build on AWS.** Connecting S3, SQS and Lambda took about a full day. Permissions had to be fixed one link at a time, the queue delivered the same letter twice, and our first deploys failed. It gave us one rule for the whole project: **every write must be safe to repeat.**
- **No documented way for an add-on to speak first.** Reminders are the heart of recovery, so we built them with EventBridge and a pending reminder the client speaks, and labelled it clearly as simulated.
- **No access to real Alexa+.** The toolkit is in preview with select partners. We built our client as a simulated Alexa+ experience and tested the MCP server with MCP Inspector and MCPJam.
- **Hosting in our region.** The AgentCore starter would not deploy (“No resources defined in project”), so we moved the same container to **ECS on Fargate**.

We documented these obstacles and workarounds in our [**friction log**](https://github.com/charvimaurya/post-discharge-mcp/blob/main/docs/friction-log.md). We also collected product feedback on AWS and Alexa-related tools.

## Accomplishments that we're proud of

- 🗣️ **A companion that speaks first in our simulated client.** EventBridge-driven reminders initiate a spoken update without a user question; we distinguish that from real Alexa+ proactive capability.
- 🛑 **"I won't guess."** Our favourite line in the whole product. In healthcare AI, saying "I don't know, ask your care team" is a feature, not a failure.
- 🧩 **A connected end-to-end prototype.** Upload a synthetic PDF and generate a plan through an AWS pipeline, backed by a self-hosted MCP server with nine tools, two prompts and an MCP App.
- 🔓 **An open-source safety gate.** `discharge-letter-check` is a separate, reusable package that any team building on discharge letters can use.
- 🚨 **Emergencies without AI guesswork.** Warning signs are answered with the letter's own words, by fixed rules.
- 🔍 **Every answer is traceable.** Each reply shows the sentence and page it came from, and every tool call is visible in Developer view.
- ✅ **Tested words, not hoped-for words.** The replies for reminders, completions and warning signs are pinned by automated tests.

## What we learned

- **Honesty builds trust.** A clear "the letter doesn't say" beats a confident wrong answer, especially in health.
- **Ears are not eyes.** A long spoken list is hard to follow. AfterWard says **one next step** and also shows it on screen.
- **Ask before you write.** If two medicines are due, AfterWard asks which one. If only one is due, it records that one and says its name, so she can say “that’s wrong” to undo it. Our final test flagged this as too trusting, so **always asking first is our next fix**.
- **Assume every message arrives twice.** Idempotent writes saved us more than once.
- **Put the rules in the tools.** With real Alexa+, Alexa+ is the agent, so every safety rule lives in the MCP server and its prompts, not in our demo agent.
- **Use AI for understanding, code for certainty.** That split made AfterWard both smart and safe.

## What's next for AfterWard: A Living Recovery Plan for Alexa+

1. **Secure sign-in and patient consent**
2. **Reminder times set by the patient**
3. **Unclear instructions sent to her care team**, so "I won't guess" becomes "I've asked for you"
4. **Progress reports for family and her care team**, building on the week summary we already have
5. **One-step calling** to emergency services or her carer
6. **Integration with hospital systems**, so the letter arrives digitally
7. **Appointment booking by voice**
8. **Medicine reordering** through her pharmacy
9. **Photo letters and multilingual voice**
10. **A clinical pilot, then a global rollout**

And, when the Alexa+ toolkit is available for broader development, our goal is to offer AfterWard as a real **Alexa+ add-on**. **The current project is a hackathon prototype using synthetic records, not a clinically validated care service.**

We started with Margaret, a synthetic patient recovering from knee replacement surgery. But the problem reaches beyond one patient, one operation or one country. Discharge instructions should not become harder to follow just because someone has left the hospital.

Our ambition is to make the discharge letter **the beginning of an understandable, updatable recovery companion**, rather than the last static document a patient receives. We will need clinicians, patients and carers to help us test whether that actually improves the experience of recovery.

> **Discharge is one moment. Recovery happens every day.**  
> **AfterWard is built for everything that comes afterward.**
