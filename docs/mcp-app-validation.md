# S4: MCPJam validation

Reviewed 17 October 2026 on `charvi/mcp-app`.

## Result

| Check | Observed result |
| --- | --- |
| S2 committed | `93f72f6`, MCP prompts: ask_my_letter and morning_checkin |
| S3 committed | `430972c`, MCP App: Today card for get_today_tasks |
| Local MCP server | Started and tested at `http://127.0.0.1:8001/mcp` using Streamable HTTP |
| Bearer authentication | Missing and incorrect tokens returned HTTP 401. The configured token permitted initialization and tool/resource/prompt requests. No token values were printed. |
| MCPJam connectivity | Observed in local MCPJam Inspector 3.16.1, controlled through a real headless Chrome browser |
| Tools | MCPJam discovered all seven existing tools |
| Prompts | MCPJam discovered `ask_my_letter` and `morning_checkin`; HTTP `prompts/get` returned content for both |
| Resource | HTTP discovery/read verified `ui://afterward/today.html`, HTML content and MIME `text/html;profile=mcp-app` |
| Tool link | HTTP `tools/list` verified `_meta.ui.resourceUri` on `get_today_tasks` |
| App rendering | Observed the real Today card inside MCPJam's sandbox proxy and nested App frame, not a synthetic host or raw JSON view |
| Initial captured card | 1 of 7 tasks done, one completed walking occurrence with a tick/time, and the next knee-exercise occurrence highlighted |
| Existing web workflow | Clicked a pending walking task's Mark as done button at `http://localhost:3000/demo`. `/api/chat` returned 200; its trace confirmed `report_task_completed` succeeded. |
| Updated captured card | Another Run of `get_today_tasks` in MCPJam displayed 2 of 7 done, with both walking occurrences completed |
| Confirmation labels | Actual returned tasks had zero confirmation flags; the live card correctly showed no labels. Flagged-data rendering remains covered by the S3 synthetic fixture and automated checks. |
| Stable repeatability | PARTIAL: later reads returned 1 of 7 again. The state changed during this session; attribution was not established. Do not describe the captured 2-of-7 result as the current persistent backend state. |

The HTTP checks used the installed Python MCP client against the running HTTP server, including protocol initialization. The initial post-reset response contained seven tasks and zero completed tasks. It had changed to one completed task before the first MCPJam card capture. The live workflow then produced the observed one-to-two change. A later strongly consistent event-history query also showed a later task event; no exclusive access to the shared synthetic patient was established. No additional resets or writes were performed to hide the discrepancy.

## Scope and setup

The reset script's actual help exposed only `--help` and `--confirm`. The authorized reset completed: one current-date event removed, four base tasks reset, four base medications reset. Task occurrences expand separately, so four base tasks produced seven Today task occurrences. The card's denominator counts tasks, not medications.

The working tree already contained unrelated uncommitted security, bridge, Amplify and documentation changes. They were preserved. No application code was changed for S4, and no S4 commit, push or deployment was performed.

The MCP server, bridge and web demo were started locally. The bridge used the local MCP endpoint and had its local reminder loop disabled. Service credentials were passed through process configuration, not browser bundles or command-line values. The temporary local servers were stopped after validation. Temporary credential copies, the private startup log and raw state dumps were removed; the screenshots and clip were retained.

The existing completion path ran deterministically: the bridge logged `kind: code`. The configured fallback agent mode was `test`, with model `eu.anthropic.claude-haiku-4-5-20251001-v1:0`. This exercise is not a final-model evaluation, and no Bedrock invocation is claimed for the completion turn.

## Problems and handling

1. The sandbox initially blocked local server binding and network access. Retried with explicit execution approval.
2. MCPJam was not installed as a desktop application. Ran the official local package with `npx --yes @mcpjam/inspector@3.16.1`, following the [official installation documentation](https://github.com/MCPJam/inspector#-install). Kept its private startup access link out of tool output.
3. Closing setup browser sessions disconnected the saved server. Reconnected through the server's actions menu and kept one browser session open for discovery and App testing.
4. The Tools response pane explicitly says to use Chat for MCP Apps. Opened Chat/Playground, selected `get_today_tasks` and used Run. This created the real MCP Apps sandbox and delivered real tool output. No custom host contract or App workaround was introduced.
5. The first web write from `127.0.0.1:3000` received HTTP 403, `Request origin is not allowed`. Retried using `localhost:3000`, which matched Next.js's local request origin. This succeeded without weakening origin checks. The local hostname difference remains a development setup caveat.
6. MCPJam defaulted to Los Angeles in its client context. The captured completion time is rendered in that host timezone. Select London before the submission recording and invoke the tool again; do not describe that captured time as London time.
7. Shared demo state changed after captures. Revalidate in a coordinated window with no parallel reset, upload or completion activity before the final submission clip. The source of the later change was not identified.

## Automated checks

- `.venv-check/bin/python -m pytest -q`: **855 passed, 10 deselected in 1.81s**. The deselected tests are excluded AWS integration tests.
- `cd web && npm test`: **73 passed, 0 failed**, duration 220.016709 ms.
- The Python suite includes the S3 registration/resource tests and a JavaScript harness with **14 UI checks**, covering both result formats, malformed/missing data, escaping, progress, confirmation flags, next task selection and host-message validation.
- `git diff --check`: passed.
- Live HTTP checks: missing/incorrect bearer rejection, authenticated discovery, two prompt reads, resource MIME/HTML, tool metadata and actual task results all passed.
- Actual MCPJam discovery and sandbox rendering were observed. A synthetic browser fixture is not being used as evidence for these S4 checks.

## Evidence

Files are local temporary artifacts outside Git. Copy the wanted files into your video assets before clearing temporary files.

- `/tmp/afterward-s4-evidence/mcpjam-before.png`: observed 1-of-7 card in MCPJam.
- `/tmp/afterward-s4-evidence/mcpjam-after.png`: observed 2-of-7 response in MCPJam.
- `/tmp/afterward-s4-evidence/demo-after.png`: existing web workflow after completion.
- `/tmp/afterward-s4-evidence/mcpjam-today-4s.mp4`: four-second capture of the real rendered 2-of-7 response, assembled from 20 screen captures over 4.003 seconds. Encoded duration verified as 4.000 seconds; size 89,045 bytes. This shows the captured tool response, not an uninterrupted recording of the backend update or proof that the backend stayed at two completed tasks afterward.

The evidence was visually checked for credential fields, headers and private access links. The visible patient information is the authorized synthetic demo. No credential-bearing logs or raw patient-state dumps are part of these evidence files.

## Exact repeat and final recording steps

1. Coordinate with anyone using the shared demo patient so no resets/uploads/completions run during this check. Agree on the expected starting count.
2. Start MCP from the repository root:

   ```bash
   .venv-check/bin/python -m uvicorn app.mcp.http_server:app --host 127.0.0.1 --port 8001
   ```

3. If a fresh reset is needed, run `.venv-check/bin/python scripts/reset_demo_patient.py --confirm` once. This writes to the shared synthetic patient. Check the returned task state immediately afterward.
4. Start local MCPJam with `npx --yes @mcpjam/inspector@3.16.1`. Open the private local access link that it prints. Do not share, record or publish that link.
5. On Connect, add an HTTP/Streamable HTTP server named AfterWard local with URL `http://127.0.0.1:8001/mcp`. Choose Bearer Token from the Authentication dropdown and enter the existing configured MCP token in the masked field. If the saved server is disconnected, use its actions menu, then Reconnect. Leave this browser session open.
6. Confirm Tools lists nine tools and Prompts lists the two prompts. In Tools, select `get_today_tasks`. Its Run response shows JSON plus a Chat shortcut in this MCPJam version.
7. Open Chat/Playground, select `get_today_tasks`, choose London in the host timezone/client context, and click Run. Do not send a conversational model request just to preview the card. Verify the Today heading, count, progress bar, completed items/times and next task. Verify confirmation labels only where the actual data is flagged.
8. Start the normal local bridge/web services with matching server-side bridge credentials. Point the bridge to `http://127.0.0.1:8001/mcp` and disable `LOCAL_REMINDER_LOOP`. Open `http://localhost:3000/demo`, open today's existing plan, and click Mark as done on one pending recovery task. Check that the write succeeded.
9. Run `get_today_tasks` again in the same MCPJam session. Compare the newly rendered card with the previous response and the web result. A historical card stays historical; running the tool again is what fetches current state.
10. Capture screenshots of the seven-tool list, two-prompt list, and the card before/after. Keep auth settings and raw logs closed. If counts unexpectedly move backward, save the times and request IDs, stop claiming a controlled pass, and investigate the concurrent state change.
11. For the final clip, scroll the new card so Today, the progress indicator, completed tick/time and next task are visible. Hide auth settings, headers and private links. Record 3–5 seconds in MCPJam with the operating system's screen recorder. The supplied four-second clip is usable as an observed response preview, subject to the timezone and shared-state caveats above.

No MCP Apps protocol, auth or CSP failure requiring an application fix was observed. Stable exclusive-state reproducibility and the final London-context recording remain to be checked.
