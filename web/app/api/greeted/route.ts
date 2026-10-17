import { bridgeJson } from '../../../lib/bridge';
import { checkRequestOrigin } from '../../../lib/api-security';
import { withDemoLimits } from '../../../lib/demo-guard';
import { REQUEST_ID_HEADER, requestIdFrom } from '../../../lib/request-id';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function POST(request: Request) {
  const rejected = checkRequestOrigin(request);
  if (rejected) return rejected;
  return withDemoLimits(request, 'read', async () => {
    const requestId = requestIdFrom(request.headers);
    try {
      const result = await bridgeJson('/greeted', requestId, ['ok'], { method: 'POST' });
      return Response.json(result, { headers: { 'Cache-Control': 'no-store', [REQUEST_ID_HEADER]: requestId } });
    } catch {
      return Response.json({ error: 'Could not save the greeting.' }, { status: 502 });
    }
  });
}
