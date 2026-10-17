import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const version = require('next/package.json').version;
// AWS managed SSR documentation reviewed 2026-10-17. Revisit with AWS's
// published support matrix before increasing this ceiling.
if (Number(version.split('.')[0]) > 15) {
  console.error('Amplify deployment blocked: installed Next.js exceeds the documented managed SSR support range (12–15). Review deployment/amplify/README.md.');
  process.exitCode = 1;
}
