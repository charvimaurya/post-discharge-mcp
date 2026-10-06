# Local CareLoop test UI

From the repository root:

```sh
cd web
npm install
cp .env.example .env.local # only needed if .env.local does not exist
npm run dev
```

Open http://localhost:3000. Choose `../test_data/doc_001.pdf` and click Upload.
Node.js 22.18+ is recommended (the test command uses native TypeScript support).

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
This is a local tool bound to 127.0.0.1, with no authentication.

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
