import { withDemoLimits } from '../../../../lib/demo-guard';
// Ask the Python bridge to run the reminder check once. On AWS the EventBridge schedule does this;
// locally the /demo page asks when it opens. Only the test-only force_next=true flag is passed on
// (the bridge refuses it in production); nothing else from the browser is forwarded.
import { bridgeJson } from '../../../../lib/bridge';
import { checkRequestOrigin } from '../../../../lib/api-security';
import { productionRuntime } from '../../../../lib/runtime-config';
import { REQUEST_ID_HEADER, requestIdFrom } from '../../../../lib/request-id';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

async function handlePOST(request: Request, demoSession: string) {
  const requestId = requestIdFrom(request.headers);
  const force = new URL(request.url).searchParams.get('force_next') === 'true';
  if (force && productionRuntime(process.env)) {
    return Response.json({ error: 'This reminder option is unavailable.' }, { status: 403 });
  }
  try {
    const payload = await bridgeJson(`/reminders/check${force ? '?force_next=true' : ''}`, requestId,
      ['created', 'reason', 'pending_checkin'], {
      method: 'POST',
      cache: 'no-store',
    });
    return Response.json(payload, {
      headers: { 'Cache-Control': 'no-store', [REQUEST_ID_HEADER]: requestId },
    });
  } catch {
    console.error('Bridge /reminders/check failed', requestId);
    return Response.json({ error: 'Could not reach the AfterWard service.' }, { status: 502 });
  }
}

export async function POST(request: Request) {
  const rejected = checkRequestOrigin(request);
  if (rejected) return rejected;
  return withDemoLimits(request, 'reminder', session => handlePOST(request, session));
}
