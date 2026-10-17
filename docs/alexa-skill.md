# Running the Alexa skill locally

This guide connects the AfterWard Alexa skill (or the Alexa developer console's
test simulator) to AfterWard running on your own Windows machine. Alexa sends each
request through a Cloudflare tunnel to the bridge's `/alexa` address, and the
`/demo` page shows every Alexa turn as a "via Alexa" bubble.

All commands are for **PowerShell**, run from the **repository root** unless a
step says otherwise.

Use the synthetic demo patient only. Never type real patient details into Alexa.

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

## 9. Troubleshooting

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
