// The Alexa turns for /demo, passed through from the Python bridge with the bridge key added here.
// The browser sends only ?after=N, the last turn id it has seen.
import { bridgeHeaders, bridgeUrl } from '../../../lib/bridge';
import { REQUEST_ID_HEADER, requestIdFrom } from '../../../lib/request-id';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function GET(request: Request) {
  const requestId = requestIdFrom(request.headers);
  const after = new URL(request.url).searchParams.get('after');
  const query = after !== null && /^\d{1,9}$/.test(after) ? `?after=${after}` : '';
  try {
    const response = await fetch(`${bridgeUrl}/conversation${query}`, {
      cache: 'no-store', headers: bridgeHeaders({ [REQUEST_ID_HEADER]: requestId }),
    });
    return Response.json(await response.json(), {
      status: response.status,
      headers: { 'Cache-Control': 'no-store', [REQUEST_ID_HEADER]: requestId },
    });
  } catch (error) {
    console.error('Bridge /conversation failed:', error instanceof Error ? error.name : 'UnknownError', requestId);
    return Response.json({ error: 'Could not reach the AfterWard service.' }, { status: 502 });
  }
}
