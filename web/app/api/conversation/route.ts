import { withDemoLimits } from '../../../lib/demo-guard';
// The Alexa turns for /demo, passed through from the Python bridge with the bridge key added here.
// The browser sends only ?after=N, the last turn id it has seen.
import { bridgeJson } from '../../../lib/bridge';
import { checkRequestOrigin } from '../../../lib/api-security';
import { REQUEST_ID_HEADER, requestIdFrom } from '../../../lib/request-id';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

async function handleGET(request: Request) {
  const requestId = requestIdFrom(request.headers);
  const after = new URL(request.url).searchParams.get('after');
  const query = after !== null && /^\d{1,9}$/.test(after) ? `?after=${after}` : '';
  try {
    const payload = await bridgeJson(`/conversation${query}`, requestId, ['turns', 'latest']);
    return Response.json(payload, { headers: { 'Cache-Control': 'no-store', [REQUEST_ID_HEADER]: requestId } });
  } catch {
    // The feed is off, or the bridge is down: /demo shows nothing and keeps working.
    return Response.json({ error: 'The Alexa feed is not available.' }, { status: 502 });
  }
}

export async function GET(request: Request) {
  const rejected = checkRequestOrigin(request);
  if (rejected) return rejected;
  return withDemoLimits(request, 'read', () => handleGET(request));
}
