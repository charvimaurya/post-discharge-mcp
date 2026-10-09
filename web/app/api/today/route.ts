// Pass today's view through from the Python bridge; the browser sends no patient, date or time.
import { bridgeUrl } from '../../../lib/bridge';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function GET() {
  try {
    const response = await fetch(`${bridgeUrl}/today`, { cache: 'no-store' });
    return Response.json(await response.json(), {
      status: response.status,
      headers: { 'Cache-Control': 'no-store' },
    });
  } catch (error) {
    console.error('Bridge /today failed:', error instanceof Error ? error.name : 'UnknownError');
    return Response.json({ error: 'Could not reach the AfterWard service.' }, { status: 502 });
  }
}
