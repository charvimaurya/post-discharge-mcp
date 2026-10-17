import { bridgeHeaders, bridgeUrl } from '../../../lib/bridge';
import { protectedBridgeFetch, publicBridgePayload } from '../../../lib/bridge-response';
import { checkRequestOrigin } from '../../../lib/api-security';
import { withDemoLimits } from '../../../lib/demo-guard';
import { REQUEST_ID_HEADER, requestIdFrom } from '../../../lib/request-id';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function POST(request: Request) {
  const rejected = checkRequestOrigin(request);
  if (rejected) return rejected;
  return withDemoLimits(request, 'reset', async session => {
    const requestId = requestIdFrom(request.headers);
    try {
      const headers = await bridgeHeaders(requestId);
      const response = await protectedBridgeFetch(`${bridgeUrl()}/reset`, {
        method: 'POST', headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: session }),
      });
      if (!response.ok) return Response.json({ error: 'Could not reset the demo. Please try again.' }, { status: response.status });
      await publicBridgePayload(response, headers['X-Bridge-Key'], []);
      return Response.json({ reset: true }, { headers: { [REQUEST_ID_HEADER]: requestId } });
    } catch {
      return Response.json({ error: 'Could not reset the demo. Please try again.' }, { status: 502 });
    }
  });
}
