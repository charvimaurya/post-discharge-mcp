// Ask the Python bridge to run the reminder check once. On AWS the EventBridge schedule does this;
// locally the /demo page asks when it opens. Only the test-only force_next=true flag is passed on
// (the bridge refuses it in production); nothing else from the browser is forwarded.
import { bridgeHeaders, bridgeUrl } from '../../../../lib/bridge';
import { REQUEST_ID_HEADER, requestIdFrom } from '../../../../lib/request-id';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function POST(request: Request) {
  const requestId = requestIdFrom(request.headers);
  const force = new URL(request.url).searchParams.get('force_next') === 'true';
  try {
    const response = await fetch(`${bridgeUrl}/reminders/check${force ? '?force_next=true' : ''}`, {
      method: 'POST',
      headers: bridgeHeaders({ [REQUEST_ID_HEADER]: requestId }),
      cache: 'no-store',
    });
    return Response.json(await response.json(), {
      status: response.status,
      headers: { 'Cache-Control': 'no-store', [REQUEST_ID_HEADER]: requestId },
    });
  } catch (error) {
    console.error('Bridge /reminders/check failed:', error instanceof Error ? error.name : 'UnknownError', requestId);
    return Response.json({ error: 'Could not reach the AfterWard service.' }, { status: 502 });
  }
}
