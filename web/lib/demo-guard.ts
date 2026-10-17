import 'server-only';
import { DynamoDBClient } from '@aws-sdk/client-dynamodb';
import { DynamoDBDocumentClient } from '@aws-sdk/lib-dynamodb';
import { bridgeHeaders } from './bridge';
import { productionRuntime } from './runtime-config';
import { clientAddress, demoCounters, demoIdentity, memoryCounters, type DemoAction } from './demo-limits';

import { distributedConsume } from './demo-counter-store';

const local = memoryCounters();

export async function withDemoLimits(request: Request, action: DemoAction, handler: (session: string) => Promise<Response>): Promise<Response> {
  const production = productionRuntime(process.env);
  let identity: ReturnType<typeof demoIdentity>;
  let allowed: boolean;
  let retry = 3600;
  try {
    const now = Math.floor(Date.now() / 1000);
    const headers = await bridgeHeaders();
    const key = headers['X-Bridge-Key'];
    const ip = clientAddress(request, production, process.env.DEMO_TRUSTED_PROXY_HOPS);
    identity = demoIdentity(request, key, now, production);
    const rules = demoCounters(action, identity.session, identity.expires, ip, key, now);
    retry = Math.max(...rules.map(rule => rule.expires - now));
    if (production) {
      const table = process.env.DEMO_LIMIT_TABLE;
      if (!table) throw new Error('Demo limits are not configured.');
      const client = DynamoDBDocumentClient.from(new DynamoDBClient({ region: process.env.AFTERWARD_AWS_REGION || process.env.AWS_REGION, maxAttempts: 2 }));
      allowed = await distributedConsume(rules, table,
        command => client.send(command, { abortSignal: AbortSignal.timeout(5000) }));
    } else allowed = await local(rules, now);
  } catch {
    return Response.json({ error: 'Demo protection is unavailable. Please try again later.' }, { status: 503, headers: { 'Cache-Control': 'no-store' } });
  }
  const response = allowed ? await handler(identity.session) : Response.json({ error: 'Demo limit reached. Please try again later.' }, { status: 429, headers: { 'Retry-After': String(retry) } });
  response.headers.set('Set-Cookie', identity.cookie);
  response.headers.set('Cache-Control', 'no-store');
  return response;
}
