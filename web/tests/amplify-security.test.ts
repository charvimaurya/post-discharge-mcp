import { test } from 'node:test';
import assert from 'node:assert/strict';
import { bridgeEndpoint, canonicalOrigin, awsSettings } from '../lib/runtime-config.ts';
import { createBridgeKeyProvider } from '../lib/bridge-key.ts';
import { publicBridgePayload, protectedBridgeFetch } from '../lib/bridge-response.ts';
import { checkRequestOrigin } from '../lib/api-security.ts';
import { validateUpload, wrongDocumentMessage } from '../lib/upload-validation.ts';
import { runtimeEnvironment } from '../scripts/write-ssr-env.mjs';

const secret = 'test-only-service-credential-0123456789';
const config = {
  DEMO_LIMIT_TABLE: 'demo-limits', DEMO_TRUSTED_PROXY_HOPS: '1', AFTERWARD_RUNTIME: 'amplify', AFTERWARD_AWS_REGION: 'eu-west-2',
  AGENT_API_URL: 'https://bridge.example.com', APP_ORIGIN: 'https://app.example.com',
  BRIDGE_KEY_SECRET_ARN: 'arn:aws:secretsmanager:eu-west-2:123456789012:secret:bridge-test',
  DOCUMENT_BUCKET: 'test-documents', RECOVERY_STATE_TABLE: 'test-state', TEST_PATIENT_ID: 'demo_patient_001',
};

test('production rejects missing settings, HTTP endpoints and credential-bearing URLs', () => {
  assert.equal(bridgeEndpoint({}), 'http://127.0.0.1:8002');
  for (const url of ['', 'http://127.0.0.1:8002', 'https://user:pass@bridge.example.com', 'https://bridge.example.com/path']) {
    assert.throws(() => bridgeEndpoint({ ...config, AGENT_API_URL: url }));
  }
  assert.throws(() => awsSettings({ NODE_ENV: 'production' }));
  assert.throws(() => canonicalOrigin({ NODE_ENV: 'production' }));
});

test('production never falls back to a direct key; local development can use one', async () => {
  const provider = createBridgeKeyProvider(async () => { throw new Error('must not load'); }, () => ({ NODE_ENV: 'production', BRIDGE_KEY: secret }));
  await assert.rejects(provider(), /not configured/);
  assert.equal(await createBridgeKeyProvider(async () => '', () => ({ BRIDGE_KEY: secret }))(), secret);
});

test('secret requests deduplicate, cache briefly, refresh and fail closed after expiration', async () => {
  let calls = 0; let clock = 0; let fail = false;
  const provider = createBridgeKeyProvider(async arn => {
    calls++; assert.equal(arn, config.BRIDGE_KEY_SECRET_ARN);
    if (fail) throw new Error('secret service unavailable');
    return secret;
  }, () => config, () => clock);
  assert.deepEqual(await Promise.all([provider(), provider(), provider()]), [secret, secret, secret]);
  assert.equal(calls, 1);
  clock = 300_001; fail = true;
  await assert.rejects(provider());
  fail = false; assert.equal(await provider(), secret); assert.equal(calls, 3);
});

test('empty, short and multiline Secrets Manager values fail closed', async () => {
  for (const value of ['', 'short', secret + '\nunsafe']) {
    await assert.rejects(createBridgeKeyProvider(async () => value, () => config)());
  }
});

test('bridge success payloads whitelist fields and redact reflected credentials recursively', async () => {
  const payload = await publicBridgePayload(Response.json({
    response: `reflected ${secret}`, help: { [secret]: [secret] }, debug: secret,
  }), secret, ['response', 'help']);
  assert.deepEqual(payload, { response: 'reflected [redacted]', help: { '[redacted]': ['[redacted]'] } });
  await assert.rejects(publicBridgePayload(new Response(secret, { status: 500 }), secret, ['response']),
    error => !String(error).includes(secret));
});

test('bridge fetch refuses redirects and disables caching', async () => {
  const original = globalThis.fetch;
  try {
    globalThis.fetch = (async (_input, init) => {
      assert.equal(init?.redirect, 'error'); assert.equal(init?.cache, 'no-store');
      assert.ok(init?.signal instanceof AbortSignal);
      return Response.json({});
    }) as typeof fetch;
    await protectedBridgeFetch('https://bridge.example.com', { redirect: 'follow', cache: 'force-cache' });
  } finally { globalThis.fetch = original; }
});

test('origin checks reject cross-site requests, allow same-origin and fail closed without config', () => {
  assert.equal(checkRequestOrigin(new Request(config.APP_ORIGIN, { headers: { Origin: config.APP_ORIGIN } }), config), undefined);
  assert.equal(checkRequestOrigin(new Request(config.APP_ORIGIN, { headers: { Origin: 'https://attacker.example' } }), config)?.status, 403);
  assert.equal(checkRequestOrigin(new Request(config.APP_ORIGIN, { headers: { 'Sec-Fetch-Site': 'cross-site' } }), config)?.status, 403);
  assert.equal(checkRequestOrigin(new Request(config.APP_ORIGIN), { NODE_ENV: 'production' })?.status, 503);
});

test('SSR env artifact contains only allowlisted configuration, never inherited AWS credentials or arbitrary env', () => {
  const text = runtimeEnvironment({ ...config, AWS_ACCESS_KEY_ID: 'test-inherited-role-id', AWS_SECRET_ACCESS_KEY: secret, UNRELATED_TOKEN: secret });
  assert.ok(text.includes('BRIDGE_KEY_SECRET_ARN='));
  assert.ok(!text.includes(secret)); assert.ok(!text.includes('AWS_ACCESS_KEY_ID'));
  assert.ok(!text.includes('UNRELATED_TOKEN'));
  assert.throws(() => runtimeEnvironment({ ...config, BRIDGE_KEY: secret }));
});

test('upload validation never returns upstream error text', async () => {
  const response = await validateUpload(new Uint8Array([37]), config.AGENT_API_URL,
    (async () => Response.json({ error: secret }, { status: 422 })) as typeof fetch);
  assert.equal(response.error, wrongDocumentMessage);
});
