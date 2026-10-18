import { withDemoLimits } from '../../../../lib/demo-guard';
import { boundedRequest } from '../../../../lib/demo-limits';
import { bridgeJson } from '../../../../lib/bridge';
import { checkRequestOrigin } from '../../../../lib/api-security';
import { REQUEST_ID_HEADER, requestIdFrom } from '../../../../lib/request-id';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function POST(request: Request) {
  const rejected = checkRequestOrigin(request);
  if (rejected) return rejected;
  return withDemoLimits(request, 'chat', async () => {
    const requestId = requestIdFrom(request.headers);
    let body: unknown;
    try { body = await (await boundedRequest(request, 2048)).json(); }
    catch { return Response.json({ error: 'Choose one scheduled task.' }, { status: 400 }); }
    if (!body || typeof body !== 'object' || Object.keys(body).length !== 1 || !('occurrence_id' in body)
        || typeof body.occurrence_id !== 'string' || !body.occurrence_id.trim() || body.occurrence_id.length > 512) {
      return Response.json({ error: 'Choose one scheduled task.' }, { status: 400 });
    }
    try {
      const payload = await bridgeJson('/tasks/complete', requestId, ['response', 'tool_trace', 'source', 'help'], {
        method: 'POST', body: JSON.stringify({ occurrence_id: body.occurrence_id.trim() }),
      });
      return Response.json(payload, { headers: { 'Cache-Control': 'no-store', [REQUEST_ID_HEADER]: requestId } });
    } catch {
      return Response.json({ error: 'Could not save that task. Please refresh your plan and try again.' },
        { status: 502, headers: { 'Cache-Control': 'no-store' } });
    }
  });
}
