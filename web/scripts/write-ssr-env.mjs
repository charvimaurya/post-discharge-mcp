import { writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { bridgeEndpoint, awsSettings, canonicalOrigin } from '../lib/runtime-config.ts';

export function runtimeEnvironment(input) {
  if (input.BRIDGE_KEY) {
    throw new Error('Remove static credentials from Amplify build environment; use a compute role and Secrets Manager.');
  }
  const env = { ...input, AFTERWARD_RUNTIME: 'amplify' };
  const settings = awsSettings(env);
  if (!/^[1-5]$/.test(env.DEMO_TRUSTED_PROXY_HOPS || '')) throw new Error('Trusted proxy hops are required.');
  const arn = env.BRIDGE_KEY_SECRET_ARN;
  if (!arn?.startsWith('arn:aws:secretsmanager:')) throw new Error('A bridge key secret ARN is required.');
  const allowed = {
    AFTERWARD_RUNTIME: 'amplify', AFTERWARD_AWS_REGION: settings.region,
    AGENT_API_URL: bridgeEndpoint(env), APP_ORIGIN: canonicalOrigin(env),
    BRIDGE_KEY_SECRET_ARN: arn, DOCUMENT_BUCKET: settings.bucket,
    RECOVERY_STATE_TABLE: settings.table, TEST_PATIENT_ID: settings.patientId,
    DEMO_LIMIT_TABLE: env.DEMO_LIMIT_TABLE, DEMO_TRUSTED_PROXY_HOPS: env.DEMO_TRUSTED_PROXY_HOPS,
  };
  for (const value of Object.values(allowed)) {
    if (!value || /[\r\n]/.test(value)) throw new Error('Invalid runtime configuration.');
  }
  return Object.entries(allowed).map(([name, value]) => `${name}=${JSON.stringify(value)}`).join('\n') + '\n';
}
if (process.argv[1] === fileURLToPath(import.meta.url)) {
  writeFileSync(new URL('../.env.production', import.meta.url), runtimeEnvironment(process.env), { mode: 0o600 });
}
