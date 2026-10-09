// Pass a chat message through to the Python bridge; only message and session_id are forwarded.
import { bridgeUrl } from '../../../lib/bridge';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function POST(request: Request) {
  let body: unknown;
  try { body = await request.json(); }
  catch { return Response.json({ error: 'Expected JSON with a message.' }, { status: 400 }); }

  const { message, session_id } = (body ?? {}) as { message?: unknown; session_id?: unknown };

  try {
    const response = await fetch(`${bridgeUrl}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, session_id }),
      cache: 'no-store',
    });
    return Response.json(await response.json(), {
      status: response.status,
      headers: { 'Cache-Control': 'no-store' },
    });
  } catch (error) {
    console.error('Bridge /chat failed:', error instanceof Error ? error.name : 'UnknownError');
    return Response.json({ error: 'Could not reach the AfterWard service.' }, { status: 502 });
  }
}
