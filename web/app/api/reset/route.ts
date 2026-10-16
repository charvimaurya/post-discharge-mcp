// Reset the demo patient for the "Reset demo" button. Only the session_id is forwarded, and the
// bridge key is added here on the server, so the browser never sees it.
import { bridgeHeaders, bridgeUrl } from '../../../lib/bridge';
import { REQUEST_ID_HEADER, requestIdFrom } from '../../../lib/request-id';
import { resetDemo } from '../../../lib/reset';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function POST(request: Request) {
  const requestId = requestIdFrom(request.headers);
  let body: unknown;
  try { body = await request.json(); } catch { body = {}; }
  const { session_id } = (body ?? {}) as { session_id?: unknown };
  const sessionId = typeof session_id === 'string' ? session_id : undefined;

  const result = await resetDemo(bridgeUrl, fetch, requestId, sessionId, bridgeHeaders());
  if (!result.ok) console.error('Bridge /reset failed:', result.status, requestId);
  return Response.json(result.ok ? { reset: true } : { error: result.error }, {
    status: result.ok ? 200 : result.status,
    headers: { 'Cache-Control': 'no-store', [REQUEST_ID_HEADER]: requestId },
  });
}
