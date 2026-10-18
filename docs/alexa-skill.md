# Running the Alexa skill locally

This guide connects the AfterWard Alexa skill (or the Alexa developer console's
test simulator) to AfterWard running on your own Windows machine. Alexa sends each
request through a Cloudflare tunnel to the bridge's `/alexa` address, and the
`/demo` page shows every Alexa turn as a "via Alexa" bubble.

All commands are for **PowerShell**, run from the **repository root** unless a
step says otherwise.

Use the synthetic demo patient only. Never type real patient details into Alexa.

For sync testing, use the isolated automated procedure in
[data-synchronisation.md](data-synchronisation.md). Do not reset or complete tasks
against shared Margaret data without approval. Idle reset is now off by default;
keep `DEMO_IDLE_RESET_HOURS=0` while checking that completions persist. A positive
setting explicitly enables the previous demo reset behaviour.

## 1. Before you start

Install these once.

**Python packages** (Python 3.11):

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

**Web app packages** (Node.js 24):

```powershell
cd web; npm install; cd ..
```

**cloudflared** (the tunnel):

```powershell
winget install --id Cloudflare.cloudflared
```

If PowerShell then says `cloudflared` is "not recognized", reload the PATH in
that terminal (or just open a new terminal):

```powershell
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
```

You also need an **Alexa developer account** with the AfterWard custom skill
(invocation name `after ward`, language **English (UK)**).

## 2. Settings in `.env`

Copy `.env.example` to `.env` in the repository root, and `web/.env.example` to
`web/.env.local`. Never commit either file.

**`BRIDGE_KEY` must be exactly the same value in both files.** Choose one private
random string and set it as `BRIDGE_KEY=<your-private-key>` in `.env` (repository
root) and again in `web/.env.local`. If the two differ, the bridge refuses the web
app: `/demo` cannot load the plan or reset, and no "via Alexa" bubbles appear.

These are the keys that matter for Alexa. The values below are placeholders:

```text
# Alexa
ALEXA_SKILL_ID=<your-skill-id>
ALEXA_VERIFY_SIGNATURE=true
ALEXA_VERIFY_TIMESTAMP=true
ALEXA_AGENT_TIMEOUT_SECONDS=7

# Clock and connections
CLOCK_MODE=real
DEMO_FIXED_NOW=2026-10-23T07:00:00+01:00
MCP_URL=http://127.0.0.1:8001/mcp
ALEXA_FEED_ENABLED=true
BRIDGE_KEY=<your-private-key>

# S3 (the letter upload bucket and the letter search index)
DOCUMENT_BUCKET=<your-document-bucket>
S3_VECTOR_BUCKET=<your-vector-bucket>
S3_VECTOR_INDEX=afterward-discharge-index
```

- `ALEXA_SKILL_ID` is the `amzn1.ask.skill....` ID shown in the developer
  console. Requests from any other skill are refused.
- Keep both `ALEXA_VERIFY_...` settings `true`. They check that the request
  really came from Alexa and is not old.
- `ALEXA_AGENT_TIMEOUT_SECONDS` is how long the bridge waits for an answer
  before Alexa says "Give me a moment, then ask me again." Alexa itself waits
  about 8 seconds.
- `CLOCK_MODE` stays `real` in `.env`. The bridge command in step 3 switches to
  the demo clock for that terminal only.
- `S3_VECTOR_BUCKET` and `S3_VECTOR_INDEX` must match the ones the deployed
  letter processor writes to, or letter questions find nothing.

## 3. Start five terminals, in this order

Open five PowerShell terminals, all in the repository root. Wait for each one to
be ready before starting the next.

### Terminal 1: MCP server (port 8001)

```powershell
.\.venv\Scripts\python.exe scripts\run_test_mcp.py --now 2026-10-23T07:00:00+01:00 --port 8001
```

**Ready when** you see `Uvicorn running on http://127.0.0.1:8001`.

### Terminal 2: Bridge (port 8002)

Paste this as **one line**:

```powershell
$env:ALEXA_FEED_ENABLED='true'; $env:MCP_URL='http://127.0.0.1:8001/mcp'; $env:CLOCK_MODE='demo'; $env:DEMO_FIXED_NOW='2026-10-23T07:00:00+01:00'; $env:PYTHONUNBUFFERED='1'; .\.venv\Scripts\python.exe scripts\run_web_bridge.py --port 8002
```

**Ready when** you see `Uvicorn running on http://127.0.0.1:8002`.

Always use the full line. Settings typed in the terminal win over `.env`, and
this machine may have a Windows-wide `MCP_URL` that points at the cloud server;
without the full line, every turn fails or the clock is wrong.
`PYTHONUNBUFFERED` makes log lines appear straight away.

The local bridge launcher also supplies the `certifi` CA bundle if Python has
no default trusted CA certificates. This addresses macOS Python installations
where downloading Alexa's signing certificate fails with
`CERTIFICATE_VERIFY_FAILED`. Explicit `SSL_CERT_FILE` or `SSL_CERT_DIR` settings
are preserved. Restart the bridge with this script after updating it. This does
not disable HTTPS verification or Alexa signature checks; direct `uvicorn`
invocations do not run the launcher's fallback.

For liveness checks, use `http://127.0.0.1:8002/bridge/health`, which returns
`{"status":"ok"}` without credentials. `/health` is not a registered health
route and returns 401 without the bridge key. That 401 does not diagnose Alexa:
`POST /alexa` uses Amazon's signature, timestamp and skill-ID checks instead.
An unsigned curl request to `/alexa` should be refused.

### Terminal 3: Web app (port 3000)

```powershell
cd web; npm run dev
```

**Ready when** you see `Ready` and `http://127.0.0.1:3000`. Open
`http://127.0.0.1:3000/demo` in your browser.

### Terminal 4: Tunnel

```powershell
cloudflared tunnel --url http://127.0.0.1:8002
```

**Ready when** it prints a box with an address like
`https://<tunnel-name>.trycloudflare.com`, followed by `Registered tunnel
connection`. Copy that address; you need it in step 4. Leave this terminal open.

### Terminal 5: Reset

Use this terminal whenever you want a fresh day for the demo patient:

```powershell
$env:CLOCK_MODE='demo'; $env:DEMO_FIXED_NOW='2026-10-23T07:00:00+01:00'; .\.venv\Scripts\python.exe scripts\reset_demo_patient.py --confirm
```

**Done when** it prints `Patient reset:` followed by how many items, tasks and
medications were reset. The **Reset demo** button on `/demo` does the same and
also clears the "via Alexa" bubbles.

## 4. Connect Alexa to your machine

In the [Alexa developer console](https://developer.amazon.com/alexa/console/ask),
open the skill, then **Build → Endpoint**:

1. Choose **HTTPS**.
2. In **Default Region**, paste the tunnel address with `/alexa` on the end:
   `https://<tunnel-name>.trycloudflare.com/alexa`
3. Under the certificate options, choose **My development endpoint is a
   sub-domain of a domain that has a wildcard certificate from a certificate
   authority**.
4. Click **Save Endpoints**.

**Every time the tunnel restarts, it gets a new address.** Paste the new address
into the Endpoint page **and click Save Endpoints again**. An address that was
edited but not saved does not count.

## 5. Rebuild the interaction model

Do this the first time, and again after any change to
[`skill-package/interactionModels/custom/en-GB.json`](../skill-package/interactionModels/custom/en-GB.json):

1. In the console, go to **Build → Interaction Model → JSON Editor**.
2. Replace everything in the editor with the contents of `en-GB.json` (or drag
   the file onto the editor).
3. Click **Save**, then **Build**. Wait for the "build successful" message.

### Walk-completion checks after a model update

The local model includes these completion samples. In the console's en-GB test
simulator, open the skill and check the recognised intent and `query` value:

| Phrase | Intent | `query` |
| --- | --- | --- |
| I just came back from my walk | `CameBackFromIntent` | my walk |
| I finished my morning walk | `FinishedIntent` | my morning walk |
| I completed my walk | `CompletedIntent` | my walk |

`FinishedIntent` normalises its opening to "I've finished" before calling the
shared recovery service. The activity and any morning qualifier stay in the slot.
Only a clearly matched scheduled occurrence may be saved. Multiple matching tasks
or multiple walks in the named part of the day must prompt for clarification.

Offline tests cover sample templates, slot forwarding, the real ASK handler,
task matching and event persistence using an isolated patient with in-memory
storage. These do not verify Amazon's hosted NLU, device speech recognition or
live DynamoDB. Simulator and device validation remain pending until the model is
rebuilt. Any save/read-back test must use an isolated environment; do not reset or
complete tasks for the shared demo patient without approval.

## 6. Stop and restart

- **Stop** a terminal: press `Ctrl+C`. If it asks `Terminate batch job (Y/N)?`,
  type `Y` and press Enter.
- **Restart** it: press the up arrow to bring back the last command, then Enter.
- If you restart terminal 4 (the tunnel), repeat step 4 with the new address.

**Port 3000 stuck** ("port 3000 is in use" or the web app starts on 3001): a
previous web app is still running. Free the port, then start terminal 3 again:

```powershell
Get-NetTCPConnection -LocalPort 3000 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

## 7. Quick check

1. In terminal 5, run the reset.
2. Refresh `/demo`. It should show **Margaret**, **0 of 13** done, at **7:00 am**.
3. In the console, open the **Test** tab and set testing to **Development**.
4. Type `open after ward`. Alexa greets Margaret and says what is next.
5. Type `I'm back from my walk.`
6. On `/demo`, the walk turns green, and a **via Alexa** bubble shows what you
   typed and what Alexa replied.

## 8. What Alexa understands

Alexa only passes a sentence to AfterWard if it **starts with an opening the
skill knows**. Some examples:

| To... | Start with... | Example |
| --- | --- | --- |
| Say something is done | I'm back from, I've done, I've finished, I've taken, I've had, I've been for | "I've taken my paracetamol" |
| Ask a question | when can I, can I, should I, how long, is it safe to, what does my letter say about | "when can I drive" |
| Say you feel unwell | I feel, I'm feeling, I've got, my, I fell, I'm in pain, I'm short of breath | "my wound is red" |
| Ask about the day | what's next, what's my plan for today, and after that | "what's next" |
| Say anything else | tell it ..., tell after ward ..., say ... | "tell it I slept badly" |

The long "I am..." and "I have..." forms work too: "I am back from my walk",
"I have taken my tablets", "I am feeling dizzy".

Tips:

- Type **one sentence at a time** and wait for the reply.
- **Don't type "Alexa"** in the simulator. It is only for speaking to a device.
- If a sentence does not work, start it with **"tell it"**.

The full list of openings is in
[`en-GB.json`](../skill-package/interactionModels/custom/en-GB.json).

## 9. Recording a demo

### Before every take

1. Restart the bridge (terminal 2) with the full one-line command. Restarting
   the bridge clears chat memory, so old test lines can't leak into the take.
2. Run the reset (terminal 5).
3. Check `/demo` shows **Margaret**, **0 of 13**, at **7:00 am**.
4. Warm up with `what's next`. Never warm up with a symptom line.
5. Block the `/demo` microphone for Alexa scenes, so only Alexa hears you.
6. Keep the laptop plugged in, with sleep turned off.

### Tested Alexa lines

Use these exact lines:

1. `open after ward`
2. `I'm back from my walk.`
3. `I've had my breakfast, and I've taken my medicine.`
4. `I've taken both. How long do I take them for?`

   Exception to one-sentence-at-a-time: tested as a single turn.
5. `can I drive`
6. `my calf is swollen.`

Lines 1 to 4 must be used in that order, because each one depends on the one
before. Lines 5 and 6 can be used anywhere after line 1, but line 6 must be the
last Alexa line: its emergency reply ends the session, so anything after it needs
`open after ward` again.

### If Alexa fails mid-take

Say or type the same line on `/demo` instead, and caption that scene
"Simulated Alexa+ (web)".

### Captions

- Alexa scenes: **Real Alexa skill · Alexa developer console**
- Web scenes: **Simulated Alexa+ (web)**

### Privacy

Blur your name, email and account ID wherever the Alexa developer console shows
them.

## 10. Troubleshooting

### "The requested skill did not provide a valid response"

Check each part in this order, and stop at the first one that is wrong:

1. **MCP (terminal 1).** Is it still running? If not, restart it.
2. **Bridge (terminal 2).** Did a new line mentioning `/alexa` (an
   `alexa_request` line) appear when you typed? If there is an error under it,
   restart the bridge with the full one-line command. If nothing appeared at all,
   Alexa is not reaching your machine; check the next two.
3. **Tunnel (terminal 4).** Is it still running? If it stopped, restart it and
   copy the new address.
4. **Endpoint saved.** Does the Endpoint page show the current tunnel address
   with `/alexa` on the end, with the wildcard certificate option, and did you
   click **Save Endpoints** after the last change?

### Alexa says "Good afternoon", or the time or tasks are wrong

The bridge was started without the full one-line command, so it is on the real
clock. Stop terminal 2 and start it again with the full line from step 3.

### A reply mentions something you did not say

The bridge remembers the recent conversation. Restart terminal 2 to clear it.

### Typing "stop" gets no reply

That is normal when the skill is not open. Type `open after ward` first.
