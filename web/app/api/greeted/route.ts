// Tell the Python bridge the page has shown today's greeting, so the next visit today says
// "Welcome back" instead of "Good morning". Nothing from the browser is forwarded.
import { bridgeUrl } from '../../../lib/bridge';
import { REQUEST_ID_HEADER, requestIdFrom } from '../../../lib/request-id';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function POST(request: Request) {
  const requestId = requestIdFrom(request.headers);
  try {
    const response = await fetch(`${bridgeUrl}/greeted`, {
      method: 'POST',
      headers: { [REQUEST_ID_HEADER]: requestId },
      cache: 'no-store',
    });
    return Response.json(await response.json(), {
      status: response.status,
      headers: { 'Cache-Control': 'no-store', [REQUEST_ID_HEADER]: requestId },
    });
  } catch (error) {
    console.error('Bridge /greeted failed:', error instanceof Error ? error.name : 'UnknownError', requestId);
    return Response.json({ error: 'Could not reach the AfterWard service.' }, { status: 502 });
  }
}
