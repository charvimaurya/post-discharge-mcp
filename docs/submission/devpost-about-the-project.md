## At a glance

> **AfterWard turns a hospital discharge letter into a daily recovery plan that speaks first, on Alexa+.**

- 🎥 **Demo video:** [ADD LINK] · 💻 **Repo:** [ADD LINK] · 🔓 **Open-source safety gate:** [ADD LINK] · 📝 **Friction log:** [ADD LINK]
- 🧰 **Self-hosted MCP server** (MCP spec 2025-11-25, Streamable HTTP) on Amazon ECS: **9 tools, 2 prompts and an MCP App**
- ☁️ **Built on AWS:** Bedrock (Claude and Titan Embeddings), S3, S3 Vectors, SQS, Lambda, DynamoDB, EventBridge Scheduler, ECS on Fargate, CloudWatch, Secrets Manager
- 🛡️ **Safety lives in tested code, not prompts:** [N] automated tests passing
- 🧪 **How judges can test:** see "How judges can test" in the README

## Inspiration

> **7:00 on a Friday morning.** Margaret, 68, is one week home after a knee replacement. Nobody has asked anything, but the screen beside her lights up and speaks:
>
> *"Good morning, Margaret. I hope you slept well. You have about thirty minutes until your morning walk, at half past seven."*

That moment is why we built AfterWard.

When a patient leaves hospital, they go home with a few sheets of paper. From then on, it is up to them and the people who care for them to remember everything: which medicine is due, what they are allowed to do, when the follow-up is, and which warning signs mean "call now". They do this while tired, sore and often scared.

Everything they need is written down. But **paper cannot tell you what matters today, it cannot notice that you already did your walk, and it cannot remind you.**

In 2023, US adults had **3,769,100 hospital readmissions within 30 days**, a readmission rate of **13.5%** ([AHRQ HCUP, Nationwide Readmissions Database 2023, Table A6](https://hcup-us.ahrq.gov/db/nation/nrd/NRDIntroduction2023.pdf)). Hospitals do the hard part on the ward. We wanted to help with the part that happens **after the ward**, at home. That is where our name comes from.

🔴 **Our mission: no one should have to remember their recovery alone.**

## What it does

AfterWard is a **proactive voice companion for Alexa+**. Upload a discharge letter once, and it becomes a living recovery plan that talks to you every day.

- 📄 **It builds the plan for you.** Medicines, walks, exercises, appointments, restrictions and warning signs, each one keeping the exact sentence it came from. Nobody types anything in.
- 🔔 **It speaks first.** Before something is due, AfterWard starts the conversation. She never has to ask.
- ✅ **It remembers what you have done.** *"I'm back from my walk."* → *"Well done, Margaret, that's your morning walk done. Next is your paracetamol and blood thinner, after breakfast."*
- 📖 **It answers from her own letter.** *"What does my letter say about driving?"* AfterWard quotes the instruction and highlights the sentence on screen, with the page number.
- 🛑 **It never guesses.** Her blood thinner has no end date in the letter. AfterWard says so, won't invent one, and tells her to ask her care team.
- 🚨 **It takes warning signs seriously.** *"My calf is swollen and I'm a bit short of breath."* → the letter's own emergency instruction, word for word, chosen by fixed rules. No AI decides in an emergency.

| An ordinary reminder or chatbot | AfterWard |
|---|---|
| Waits to be asked | **Speaks first**, before something is due |
| You type the reminders in | **Builds the plan** from the discharge letter |
| Forgets what you did | **Remembers** what is done and what is next |
| Fills gaps with a confident guess | **Says "I won't guess"** and points to the care team |
| Answers from the internet | **Quotes your own letter**, and shows the sentence |

It is **voice first**, because a patient's hands may be on a walking frame, but **not voice only**: large cards show what is next, and everything also works by typing or one tap.

*The Alexa+ experience is simulated in a web app, as the hackathon rules allow, and labelled "Simulated Alexa+" on every screen. All patient data is synthetic.*

## How we built it

Our design rule: **AI where understanding is needed, fixed rules where safety matters.**

**1. A letter becomes a plan**

- The letter is uploaded to **Amazon S3**, which sends an event to **Amazon SQS**. An **AWS Lambda** worker picks it up, with a dead-letter queue and an **Amazon CloudWatch** alarm for anything that keeps failing.
- **Claude on Amazon Bedrock** reads the letter into a structured plan using structured output.
- Every item then passes our **open-source safety gate**, `discharge-letter-check`. Fixed rules, not a second model, check every field. A missing dose holds the medicine back. A missing end date keeps today's doses but marks the end date as "not stated". Unclear is flagged, **never guessed**.
- The plan is saved in **Amazon DynamoDB**, and the letter is chunked and indexed in **Amazon S3 Vectors** with Titan Text Embeddings V2, filtered to one patient.
- Every step is **idempotent**: if a message arrives twice, nothing is processed or charged twice.

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

- A **Next.js** simulated Alexa+ client, drawn to Amazon's public Alexa+ MCP add-on design guide: large text, one next step at a time, and the source sentence on every card.
- A **Developer view** shows every MCP tool call live, so judges can see that each reply comes from a real tool call.
- A **classic Alexa custom skill**, so the same plan also works on a real Alexa device. (A classic skill can't speak first, so reminders stay in the simulated client.)

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

**✅ Never records a dose that didn't happen.** "Not yet" and "I forgot" block every save. Code checks that the **full** dose was taken, so a half dose is never saved as a full one. The assistant only says "recorded" after the database confirms it, and "that's wrong" undoes it with the history kept.

**🔒 Private by design.** The AI can never choose which patient it reads. Identity is set by the server after login. Letter search is filtered by patient, and storage is encrypted at rest and HTTPS-only.

**📈 Observability without patient data.** One request ID follows each message from the browser to the database. Logs keep IDs, counts and timings only: the logger itself drops anything that could be letter text, a medicine name or a patient name, and a test enforces it. Five CloudWatch metrics are built in (chat speed, tool speed, tool errors, blocked writes, upload-to-ready time), with alarms defined as code.

## Challenges we ran into

- **Our first build on AWS.** Connecting S3, SQS and Lambda took about a full day. S3's own test message broke our worker, permissions had to be fixed one link at a time, the queue delivered the same letter twice, and our first deploys failed. It gave us one rule for the whole project: **every write must be safe to repeat.**
- **A dose misread with no warning.** Reading a photographed letter, the model returned "111" as **"171"**, with no sign of doubt. In a discharge letter, a wrong digit is a wrong dose. Any medicine read from an image is now held back as **"needs confirmation"** until checked.
- **A safety rule that was too blunt.** Our first rule hid a blood thinner from the whole plan because its end date was unclear. That is unsafe in a different way. Now we flag the unclear **field**, not the whole medicine.
- **No documented way for an add-on to speak first.** Reminders are the heart of recovery, so we built them with EventBridge and a pending reminder the client speaks, and labelled it clearly as simulated.
- **No access to real Alexa+.** The toolkit is in preview with select partners. We built our client to Amazon's public design guide and tested the MCP server with MCP Inspector and MCPJam.
- **AgentCore would not deploy.** Three deploys of the AgentCore starter project in six minutes all stopped with "No resources defined in project", so we moved the same container to ECS on Fargate.

We recorded every one of these in a public **friction log**, with a concrete suggestion for Amazon on each.

## Accomplishments that we're proud of

- 🗣️ **A companion that speaks first.** AfterWard doesn't wait to be asked. That is what makes it feel like a companion and not a chatbot.
- 🛑 **"I won't guess."** Our favourite line in the whole product. In healthcare AI, saying "I don't know, ask your care team" is a feature, not a failure.
- 🧩 **A real, end-to-end system.** Upload a PDF, and a few seconds later there is a plan you can talk to, backed by a full AWS pipeline and a self-hosted MCP server with 9 tools, 2 prompts and an MCP App.
- 🔓 **An open-source safety gate.** `discharge-letter-check` is a separate, reusable package that any team building on discharge letters can use.
- 🚨 **Emergencies without AI guesswork.** Warning signs are answered with the letter's own words, by fixed rules.
- 🔍 **Every answer is traceable.** Each reply shows the sentence and page it came from, and every tool call is visible in Developer view.
- ✅ **Tested words, not hoped-for words.** The replies for reminders, completions and warning signs are pinned by automated tests.

## What we learned

- **Honesty builds trust.** A clear "the letter doesn't say" beats a confident wrong answer, especially in health.
- **Ears are not eyes.** A long spoken list is hard to follow. AfterWard says **one next step** and shows the rest on screen.
- **Ask before you write.** "I took my tablets" could mean any of them. Our own tests caught AfterWard saving one anyway, so asking which medicine first is our next fix.
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

And, when the Alexa+ toolkit opens to developers, AfterWard as a real **Alexa+ add-on**.

> *Discharge is one moment. Recovery happens every day.*
