import { canonicalOrigin, productionRuntime, type Environment } from './runtime-config.ts';

export function checkRequestOrigin(request: Request, env: Environment = process.env): Response | undefined {
  let expected: string;
  let localAliases = false;
  try {
    const configured = canonicalOrigin(env);
    expected = configured || new URL(request.url).origin;
    localAliases = !configured && !productionRuntime(env);
  }
  catch { return Response.json({ error: 'Service configuration is unavailable.' }, { status: 503, headers: { 'Cache-Control': 'no-store' } }); }
  const origin = request.headers.get('Origin');
  let matches = !origin || origin === expected;
  if (!matches && origin && localAliases) {
    try {
      const actual = new URL(origin);
      const target = new URL(expected);
      const loopback = new Set(['localhost', '127.0.0.1', '[::1]']);
      // Next.js may use its bind address instead of the browser's hostname.
      matches = actual.origin === origin && loopback.has(actual.hostname)
        && loopback.has(target.hostname) && actual.protocol === target.protocol
        && actual.port === target.port;
    } catch { matches = false; }
  }
  if (!matches || request.headers.get('Sec-Fetch-Site') === 'cross-site') {
    return Response.json({ error: 'Request origin is not allowed.' }, { status: 403, headers: { 'Cache-Control': 'no-store' } });
  }
}
