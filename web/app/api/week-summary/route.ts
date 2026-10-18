import { withDemoLimits } from '../../../lib/demo-guard';
import { bridgeJson } from '../../../lib/bridge';
import { checkRequestOrigin } from '../../../lib/api-security';
import { REQUEST_ID_HEADER, requestIdFrom } from '../../../lib/request-id';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function GET(request: Request) {
  if (new URL(request.url).searchParams.has('patient_id')) {
    return Response.json({ error: 'Patient identity is assigned by the server.' }, { status: 400 });
  }
  const rejected = checkRequestOrigin(request);
  if (rejected) return rejected;
  return withDemoLimits(request, 'read', async () => {
    const requestId = requestIdFrom(request.headers);
    try {
      const payload = await bridgeJson('/week-summary', requestId, ['week', 'timezone', 'as_of']);
      return Response.json(payload, {
        headers: { 'Cache-Control': 'no-store', [REQUEST_ID_HEADER]: requestId },
      });
    } catch {
      return Response.json({ error: 'The weekly summary could not be checked.' }, {
        status: 502, headers: { 'Cache-Control': 'no-store' },
      });
    }
  });
}
