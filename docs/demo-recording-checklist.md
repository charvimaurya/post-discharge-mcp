# Demo recording checklist

For recording the AfterWard hackathon video, under 3 minutes (aim for 2:50).
Every scene below was checked against the code on 18 October 2026 (commit `bb1aee4`).
Assistant replies are generated live: never script, re-record or dub them. The
captions describe what is on screen; they are not the assistant's words.

## Before you start: two decisions

1. **Reset Margaret before the take.** Margaret (`demo_patient_001`) is the shared
   synthetic patient. On 18 October at 12:00 her day was not fresh: the 07:30 walk
   and both morning medicines were already recorded. The reset changes shared data,
   so run it yourself, just before recording: press **Reset demo** on `/demo`, or
   `python scripts/reset_demo_patient.py --confirm`.
2. **Decide whether to upload live (scene 2).** Uploading writes to shared Margaret:
   it clears her saved history and the **deployed** document Lambda rebuilds her plan.
   That Lambda was last updated on 14 October, before later extraction changes, so
   rehearse the upload once and check the plan before the real take. If you skip the
   live upload, start at scene 3 and say the plan was built from her letter earlier.

## Services to run

Use the full commands from the [README](../README.md#start-the-three-parts) and
[Alexa guide](alexa-skill.md#3-start-five-terminals-in-this-order).

| Terminal | What | Address | Notes |
| --- | --- | --- | --- |
| 1 | MCP server | `http://127.0.0.1:8001/mcp` | Keep its log visible: scene 6 shows it |
| 2 | Python bridge | `http://127.0.0.1:8002` | `.env` must have `CLOCK_MODE=demo`, `DEMO_FIXED_NOW=2026-10-23T07:00:00+01:00`, `ALEXA_FEED_ENABLED=true`. Restart it before each take to clear chat memory |
| 3 | Web app | `http://127.0.0.1:3000` | `npm run dev` |
| 4 | Tunnel (Alexa scene only) | `cloudflared tunnel --url http://127.0.0.1:8002` | A new address each start: paste it plus `/alexa` into the Alexa console Endpoint page and **Save Endpoints** |

Keep the laptop plugged in with sleep turned off; a sleeping Mac drops the tunnel.

## Tabs and windows to open

1. The synthetic letter `test_data/letter1_margaret_knee_replacement_SYNTHETIC_v4.pdf`
   in a PDF viewer (scene 1).
2. `http://127.0.0.1:3000/demo` on the start screen.
3. Alexa developer console, **Test** tab, skill "after ward" (scene 5). Blur your
   name, email and account ID.
4. Terminal 1 (MCP server log), sized to read (scene 6).
5. https://github.com/charvimaurya/discharge-letter-check (scene 7).
6. `docs/architecture.svg` (scene 8).

Do not pre-open `/demo/recovery`: **View weekly dashboard** opens it in its own tab.

## Read-only checks before each take

These read only; none changes Margaret.

| Check | Command or action | Expect |
| --- | --- | --- |
| MCP up | `curl http://127.0.0.1:8001/health` | `{"status":"ok","service":"AfterWard MCP"}` |
| Bridge up | `curl http://127.0.0.1:8002/bridge/health` | `{"status":"ok"}` |
| Tunnel reaches the bridge | `curl -X POST https://<tunnel>/alexa -d '{}'` | HTTP 400 and an `alexa_rejected` / `signature` line in the bridge log (an unsigned test is refused; that is correct) |
| After the reset | Open `/demo`, then **Open today's plan** | **Margaret**, **Demo time** Friday 23 October **7:00 am**, **0 of 13** done (the count seen on 18 October; recheck if her plan changes) |
| Labels | Look at the screen | **SIMULATED ALEXA+** pill top right; footer "Synthetic patient data · Simulated Alexa+" |
| Microphone and speech | Say "what's next" once on `/demo` | Spoken reply. Never warm up with a symptom line. Then press Reset demo again |

## Writes that happen during the take

All on shared Margaret, all expected for a demo:

- Opening Today at 07:00 creates the morning reminder (pending check-in) and marks
  her greeted.
- Each chat turn records chat activity; replying clears the reminder.
- Scene 4 records the walk (`report_task_completed`).
- Scene 2, if recorded, replaces her plan and clears her history.

## Scenes (about 2:50)

### 1. The problem (0:00–0:15)

**Show:** the synthetic letter PDF, then the `/demo` start screen ("Discharge is one
moment. Recovery happens every day.").
**Narrate:** "Leaving hospital comes with a letter full of instructions. At home,
Margaret has to remember all of it alone. AfterWard turns that letter into a living
recovery plan. This is Simulated Alexa+, with synthetic data."
**Caption:** Synthetic patient · Simulated Alexa+

### 2. Letter to plan (0:15–0:40), optional, see decision 2

**Show:** **Upload a discharge letter** → the v4 PDF. The screen shows her letter's
lines, then **Read the letter → Check every line → Plan ready**, then the plan by
section with **Needs confirmation** chips, and the caption "Built from Margaret's
discharge letter. Nobody typed this in."
**Narrate:** "The letter goes to Amazon S3, a queue, and a Lambda that reads it with
Amazon Bedrock. Every item keeps the sentence it came from. Anything unclear is
flagged for a person, not guessed."
**Caption:** S3 → SQS → Lambda → Bedrock → DynamoDB. Processing wait shortened (only
if you cut the wait).

### 3. AfterWard speaks first (0:40–1:00)

**Show:** **Open today's plan.** At Demo time 7:00 am, AfterWard speaks first (on
18 October: "Good morning, Margaret… about thirty minutes until your morning walk,
at half past seven"). The walk card shows **Due in 30 minutes** and the caption
"Nobody set this reminder. It came from her letter." Let the real reminder play.
**Narrate (after it):** "Nobody set this reminder. It came from her letter, and
AfterWard spoke first."
**Caption:** Reminder rules run on the server · voice is the browser's own

### 4. Recording what she did (1:00–1:20)

**Say:** "I'm back from my walk."
**Show:** the reply, then the walk card moving to **Done**. Switch on **Developer
view**: `report_task_completed` and its `request_id`.
**Narrate:** "That is not just a reply. AfterWard recorded that walk through an MCP
tool, and the plan updates."
**Caption:** Recorded with the MCP tool `report_task_completed`

### 5. Answers from her letter (1:20–1:55)

**Say:** "Can I drive?"
**Show:** the reply and the letter panel with the highlighted sentence, page 1:
"Do not drive until your consultant has reviewed you at your 6-week appointment and
told you it is safe."
**Caption:** Answer shown with the letter's own sentence and page

**Say:** "How long do I take the blood thinner for?"
**Show:** the Apixaban line ("Continue as directed. Your consultant will tell you how
long to continue at your 6-week review.") and the note **Needs confirmation: the
letter gives no end date**.
**Narrate:** "When the letter does not give an end date, AfterWard says so. It does
not guess."
**Caption:** No end date in the letter, so none is invented

### 6. The same plan on Alexa (1:55–2:15)

**Before:** block the microphone on `/demo` so only Alexa hears you.
**Do:** in the Alexa console Test tab, type or say `open after ward`, then
`can I drive`.
**Show:** Alexa's reply in the console, and the same turns appearing on `/demo`.
**Caption:** Real Alexa skill · Alexa developer console · same bridge and plan
If Alexa fails, type the line on `/demo` and caption it "Simulated Alexa+ (web)".

### 7. Real MCP calls, and the open-source checker (2:15–2:40)

**Show:** Developer view's `request_id`, then terminal 1 with the matching
`"event":"tool_call"` lines for that `request_id`
(`get_today_tasks`, `get_medications`, `search_discharge_instructions`,
`report_task_completed`). Then the discharge-letter-check GitHub page (README,
tests badge).
**Narrate:** "Every read and write goes through AfterWard's own MCP server; here are
the calls in the server log. The letter checks live in a separate open-source
package, discharge-letter-check: a fixed JSON schema and rule checks, no AI, that
flag anything a person must confirm. AfterWard installs it from its v0.1.0 release."
**Caption:** Local MCP server, Streamable HTTP · discharge-letter-check, MIT

### 8. Close (2:40–2:50)

**Show:** `docs/architecture.svg` for about 5 seconds, then Today with the walk done.
**Narrate:** "From a letter to the next clear step. AfterWard is a prototype, built
with synthetic data."
**End card:** AfterWard · Simulated Alexa+ · synthetic data prototype · repository
link (and video and Devpost links once they exist).

Optional, only if time allows: **View weekly dashboard** (opens a new tab). The
calendar starts at Wed 21: 21 and 22 hold demo history added with
`scripts/seed_demo_history.py` (not recorded through the app), 23 is today, and
24 to 27 are upcoming. Do not narrate 21 and 22 as recorded by Margaret. A new letter
upload deletes the demo history; re-run the seed script afterwards.

## Do not say or show

- That the recorded MCP calls ran in the cloud. This demo uses the **local** MCP
  server; the ECS deployment is older and lacks two tools.
- Seven or eight tools: the server has **nine** tools and two prompts.
- A native Alexa+ deployment, a published skill, Amazon Polly or AgentCore.
- Any accuracy figure, "safe", "clinically validated", fewer readmissions or other
  outcome claims. The recorded model evaluation (13 of 14, synthetic tools) is not a
  clinical result.
- `.env`, tokens, `X-Bridge-Key`, the Alexa console's account details, or any real
  patient data.

## After recording

- Measure the exported length (under 3:00) and add captions.
- Check the Simulated Alexa+ label is readable in every scene.
- Press **Reset demo** if others will use Margaret next.
