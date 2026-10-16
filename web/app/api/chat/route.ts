// Pass a chat message through to the Python bridge; only message and session_id are forwarded.
import { bridgeHeaders, bridgeUrl } from '../../../lib/bridge';
import { REQUEST_ID_HEADER, requestIdFrom } from '../../../lib/request-id';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function POST(request: Request) {
  const requestId = requestIdFrom(request.headers);
  let body: unknown;
  try { body = await request.json(); }
  catch { return Response.json({ error: 'Expected JSON with a message.' }, { status: 400 }); }

  const { message, session_id } = (body ?? {}) as { message?: unknown; session_id?: unknown };

  try {
    const response = await fetch(`${bridgeUrl}/chat`, {
      method: 'POST',
      headers: bridgeHeaders({ 'Content-Type': 'application/json', [REQUEST_ID_HEADER]: requestId }),
      body: JSON.stringify({ message, session_id }),
      cache: 'no-store',
    });
    return Response.json(await response.json(), {
      status: response.status,
      headers: { 'Cache-Control': 'no-store', [REQUEST_ID_HEADER]: requestId },
    });
  } catch (error) {
    console.error('Bridge /chat failed:', error instanceof Error ? error.name : 'UnknownError', requestId);
    return Response.json({ error: 'Could not reach the AfterWard service.' }, { status: 502 });
  }
}
