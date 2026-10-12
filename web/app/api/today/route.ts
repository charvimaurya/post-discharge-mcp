// Pass today's view through from the Python bridge; the browser sends no patient, date or time.
import { bridgeUrl } from '../../../lib/bridge';
import { REQUEST_ID_HEADER, requestIdFrom } from '../../../lib/request-id';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function GET(request: Request) {
  const requestId = requestIdFrom(request.headers);
  try {
    const response = await fetch(`${bridgeUrl}/today`, { cache: 'no-store', headers: { [REQUEST_ID_HEADER]: requestId } });
    return Response.json(await response.json(), {
      status: response.status,
      headers: { 'Cache-Control': 'no-store', [REQUEST_ID_HEADER]: requestId },
    });
  } catch (error) {
    console.error('Bridge /today failed:', error instanceof Error ? error.name : 'UnknownError', requestId);
    return Response.json({ error: 'Could not reach the AfterWard service.' }, { status: 502 });
  }
}
