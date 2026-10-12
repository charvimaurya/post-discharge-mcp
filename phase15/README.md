# Phase 15: the mock-up screen, connected to your bridge

This folder adds a new page, **/demo**, to your web app. It looks like the mock-ups and gets all its data from the
routes you already have: `/api/upload`, `/api/recovery-state`, `/api/today` and `/api/chat`.
Your existing pages (`/` and `/assistant`) are not changed.

## What is in this folder

| File | Goes to | What it does |
|---|---|---|
| `web/app/demo/page.tsx` | `web/app/demo/page.tsx` | The page: start screen, building the plan, today, talking, reminder |
| `web/app/demo/parts.tsx` | `web/app/demo/parts.tsx` | The screen parts: top bar, footer, Today panel, voice panel, letter panel, developer view |
| `web/app/demo/icons.tsx` | `web/app/demo/icons.tsx` | The logo and line icons from the mock-ups |
| `web/app/demo/afterward.css` | `web/app/demo/afterward.css` | The mock-up colours and layout, only active inside the /demo page |
| `web/lib/assistant-data.ts` | `web/lib/assistant-data.ts` | Reads the bridge replies. If a field has a different name, change it here only |
| `web/lib/voice.ts` | `web/lib/voice.ts` | Browser speaking and listening (no keys, no AWS) |
| `web/tests/assistant-data.test.ts` | `web/tests/assistant-data.test.ts` | Tests for the file above |

## Steps

1. Copy the `web` folder from here into your project, so each file lands in the place shown above.
2. In a terminal, in your project's `web` folder, add the fonts:
   `npm install @fontsource/source-serif-4 @fontsource/ibm-plex-sans @fontsource/ibm-plex-mono`
3. Make the Python bridge send medicines too (see "Bridge change" below), then restart the bridge.
4. Start everything as before (MCP server on 8001, bridge on 8002, `npm run dev`).
5. Open http://127.0.0.1:3000/demo in Chrome or Edge, with the browser window full screen.
6. Check: `npm test` and `npm run typecheck` both pass.

## Bridge change (Python, app/web_bridge.py)

The Today panel needs tasks AND medicines ("0 of 11"). Today `/today` only sends tasks.

In the `/today` handler, find the line that calls the `get_today_tasks` MCP tool. Add the same call for
`get_medications`, and add it to the reply:

```python
tasks = await call_tool("get_today_tasks", {})        # this line already exists (your name may differ)
medications = await call_tool("get_medications", {})  # add this line, copying the line above
return JSONResponse({
    "clock_label": clock_label,
    "tasks": tasks,
    "medications": medications,                        # add this line
    "pending_checkin": pending_checkin,
})
```

Then add a test in `tests/test_web_bridge.py` that `/today` returns a `medications` list.

## Two small fixes so the demo matches the script

- **Name:** in `scripts/reset_demo_patient.py`, set `first_name` to `"Margaret"` on her record, so the reminder says
  "Good morning, Margaret" and not "Good morning, there".
- **Wording:** in `app/reminders/text.py`, change "I hope you're doing well." to "I hope you slept well."
  and update the expected text in `tests/test_reminder_text.py`.

## If something looks wrong

- **The Today panel is empty but /api/today works:** a field name is different. Open
  http://127.0.0.1:3000/api/today, look at the names, and adjust `readToday` in `web/lib/assistant-data.ts`.
- **No voice:** click "Open today's plan" or the start screen first. Browsers only allow speaking after a click.
- **The microphone does nothing:** use Chrome or Edge, and allow the microphone. You can always click "Type".
- **The letter panel never shows for the blood thinner question:** the bridge only sends a letter passage when the
  agent used `search_discharge_instructions`. That is expected.
