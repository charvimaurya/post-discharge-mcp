import { productionRuntime } from '../../../lib/runtime-config';
import { clientAddress, boundedRequest } from '../../../lib/demo-limits';
import { withDemoLimits } from '../../../lib/demo-guard';
// The server assigns the chat session from a signed cookie; browser session IDs are ignored.
import { bridgeJson } from '../../../lib/bridge';
import { checkRequestOrigin } from '../../../lib/api-security';
import { REQUEST_ID_HEADER, requestIdFrom } from '../../../lib/request-id';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

async function handlePOST(request: Request, demoSession: string) {
  const requestId = requestIdFrom(request.headers);
  let body: unknown;
  try { body = await (await boundedRequest(request, 16_384)).json(); }
  catch (error) { return Response.json({ error: 'Expected a small JSON message.' }, { status: error instanceof RangeError ? 413 : 400 }); }

  if (body && typeof body === 'object' && 'patient_id' in body) {
    return Response.json({ error: 'Patient identity is assigned by the server.' }, { status: 400 });
  }
  const { message } = (body ?? {}) as { message?: unknown; session_id?: unknown };
  if (typeof message !== 'string' || !message.trim() || message.length > 4000) {
    return Response.json({ error: 'Send a message of up to 4,000 characters.' }, { status: 400 });
  }

  try {
    const payload = await bridgeJson('/chat', requestId,
      ['response', 'tool_trace', 'source', 'help', 'session_id', 'request_id', 'completed'], {
      method: 'POST',
      headers: { 'X-AfterWard-Client-IP': clientAddress(request, productionRuntime(process.env), process.env.DEMO_TRUSTED_PROXY_HOPS) },
      body: JSON.stringify({ message, session_id: demoSession }),
      cache: 'no-store',
    });
    return Response.json(payload, {
      headers: { 'Cache-Control': 'no-store', [REQUEST_ID_HEADER]: requestId },
    });
  } catch {
    console.error('Bridge /chat failed', requestId);
    return Response.json({ error: 'Could not reach the AfterWard service.' }, { status: 502 });
  }
}

export async function POST(request: Request) {
  const rejected = checkRequestOrigin(request);
  if (rejected) return rejected;
  return withDemoLimits(request, 'chat', session => handlePOST(request, session));
}
