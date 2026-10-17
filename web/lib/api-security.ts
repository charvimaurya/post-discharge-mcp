import { canonicalOrigin, type Environment } from './runtime-config.ts';

export function checkRequestOrigin(request: Request, env: Environment = process.env): Response | undefined {
  let expected: string;
  try { expected = canonicalOrigin(env) || new URL(request.url).origin; }
  catch { return Response.json({ error: 'Service configuration is unavailable.' }, { status: 503, headers: { 'Cache-Control': 'no-store' } }); }
  const origin = request.headers.get('Origin');
  if ((origin && origin !== expected) || request.headers.get('Sec-Fetch-Site') === 'cross-site') {
    return Response.json({ error: 'Request origin is not allowed.' }, { status: 403, headers: { 'Cache-Control': 'no-store' } });
  }
}
