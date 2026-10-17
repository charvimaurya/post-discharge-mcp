// Only server API routes may resolve the bridge endpoint and service key.
import 'server-only';
import { GetSecretValueCommand, SecretsManagerClient } from '@aws-sdk/client-secrets-manager';
import { authenticatedBridgeHeaders } from './bridge-auth';
import { createBridgeKeyProvider } from './bridge-key';
import { bridgeEndpoint } from './runtime-config';
import { protectedBridgeFetch, publicBridgePayload } from './bridge-response';

const getKey = createBridgeKeyProvider(async arn => {
  // Default SDK credential chain resolves the Amplify compute role. No access keys.
  const client = new SecretsManagerClient({ region: process.env.AFTERWARD_AWS_REGION || process.env.AWS_REGION, maxAttempts: 2 });
  const result = await client.send(new GetSecretValueCommand({ SecretId: arn }), { abortSignal: AbortSignal.timeout(5_000) });
  return result.SecretString || '';
}, () => process.env);

export function bridgeUrl(): string { return bridgeEndpoint(process.env); }

export async function bridgeHeaders(requestId?: string): Promise<Record<string, string>> {
  return authenticatedBridgeHeaders(await getKey(), requestId);
}

export async function bridgeJson(path: string, requestId: string, fields: readonly string[], init?: RequestInit) {
  const headers = await bridgeHeaders(requestId);
  const response = await protectedBridgeFetch(`${bridgeUrl()}${path}`, {
    ...init, headers: { ...Object.fromEntries(new Headers(init?.headers)), ...headers, ...(init?.body ? { 'Content-Type': 'application/json' } : {}) },
  });
  return publicBridgePayload(response, headers['X-Bridge-Key'], fields);
}
