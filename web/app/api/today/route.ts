import { withDemoLimits } from '../../../lib/demo-guard';
// Pass today's view through from the Python bridge; the browser sends no patient, date or time.
import { bridgeJson } from '../../../lib/bridge';
import { checkRequestOrigin } from '../../../lib/api-security';
import { REQUEST_ID_HEADER, requestIdFrom } from '../../../lib/request-id';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

async function handleGET(request: Request, demoSession: string) {
  const requestId = requestIdFrom(request.headers);
  try {
    const payload = await bridgeJson('/today', requestId,
      ['clock_label', 'first_name', 'opening_greeting', 'date', 'discharge_date', 'tasks', 'medications', 'pending_checkin']);
    return Response.json(payload, {
      headers: { 'Cache-Control': 'no-store', [REQUEST_ID_HEADER]: requestId },
    });
  } catch {
    console.error('Bridge /today failed', requestId);
    return Response.json({ error: 'Could not reach the AfterWard service.' }, { status: 502 });
  }
}

export async function GET(request: Request) {
  const rejected = checkRequestOrigin(request);
  if (rejected) return rejected;
  return withDemoLimits(request, 'read', session => handleGET(request, session));
}
