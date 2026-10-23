# Local AfterWard test UI

From the repository root:

```sh
cd web
npm install
cp .env.example .env.local # only needed if .env.local does not exist
npm run dev
```

Open http://localhost:3000. Choose `../test_data/letter1_margaret_knee_replacement_SYNTHETIC_Oct20.pdf` and click Upload.
Use Node.js 24 (see `.nvmrc`; tests use native TypeScript support).

Start the Python bridge with `python scripts/run_web_bridge.py` from the root
and run the MCP server as described in the root README. Set a matching private
`BRIDGE_KEY` in root `.env` and `web/.env.local`; blank keys now fail closed.
The API routes send it to the bridge server-side. `AGENT_API_URL` defaults to
`http://127.0.0.1:8002`. Use a distinct cloud key for deployment; never prefix
the key with `NEXT_PUBLIC_`. See [bridge deployment](../deployment/bridge/README.md).

The server uses your normal AWS credential chain (for example ~/.aws/credentials
or AWS_PROFILE). No access keys belong in browser code. Configuration is in
`.env.local`; `.env.example` lists the region, bucket, table, and test patient.
The server needs S3 PutObject on the configured bucket and DynamoDB GetItem on
the configured table. The existing S3 notification/queue/Lambda pipeline must
already be running.

POST /api/upload creates a fresh ui_ document ID and stores the PDF at
patients/demo_patient_001/documents/{document_id}.pdf. S3 triggers the existing
pipeline. GET /api/recovery-state reads the current test patient's DynamoDB item.
The page polls every two seconds until BOTH document ID matches and status is
ready. A previous ready plan is ignored. After 90 seconds it shows a timeout;
processing in AWS may continue. A failed status or request produces an error.

Use one upload at a time: this test patient has one current RecoveryState, so
concurrent uploads from multiple tabs can replace each other's results.
This is a local tool bound to 127.0.0.1, with no visitor authentication.
Bridge service authentication does not isolate visitors or authorize public UI use.

Files:
- app/page.tsx: upload form, status, and recovery plan display.
- app/api/upload/route.ts: server-side S3 upload.
- app/api/recovery-state/route.ts: server-side DynamoDB read.
- lib/aws.ts: private AWS clients/configuration.
- lib/poll.ts: document-aware polling and timeout.
- tests/poll.test.ts: local polling tests, no AWS calls.

Checks:

```sh
npm test
npm run typecheck
npm run build
```

AWS Amplify SSR configuration, compute-role policy, compatibility blocker and
publication gates: [deployment guide](../deployment/amplify/README.md).

Public API routes enforce demo quotas. Local counters are in memory; cloud
requires DEMO_LIMIT_TABLE and a verified DEMO_TRUSTED_PROXY_HOPS. Upload attempts
are limited to three per signed 24-hour session, with a 4 MiB file cap. See
[the final demo test report](../docs/public-demo-final-test-report.md).
