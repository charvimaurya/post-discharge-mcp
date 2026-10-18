import { withDemoLimits } from '../../../lib/demo-guard';
import { bridgeJson } from '../../../lib/bridge';
import { checkRequestOrigin } from '../../../lib/api-security';
import { requestIdFrom } from '../../../lib/request-id';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function GET(request: Request) {
  const params = new URL(request.url).searchParams;
  const date = params.get('date') || '';
  const stamp = Date.parse(`${date}T00:00:00Z`);
  if (Array.from(params.keys()).some(key => key !== 'date') || params.getAll('date').length !== 1
      || !/^\d{4}-\d{2}-\d{2}$/.test(date) || !Number.isFinite(stamp)
      || new Date(stamp).toISOString().slice(0, 10) !== date) {
    return Response.json({ error: 'Choose one valid date only.' }, { status: 400 });
  }
  const rejected = checkRequestOrigin(request);
  if (rejected) return rejected;
  return withDemoLimits(request, 'read', async () => {
    try {
      const payload = await bridgeJson(`/recovery-day?date=${encodeURIComponent(date)}`, requestIdFrom(request.headers),
        ['kind', 'schema_version', 'date', 'timezone', 'as_of', 'scope', 'schedule_evidence', 'synthetic_demo_history', 'medications', 'tasks']);
      return Response.json(payload, { headers: { 'Cache-Control': 'no-store' } });
    } catch {
      return Response.json({ error: 'Recovery history could not be checked.' }, { status: 502, headers: { 'Cache-Control': 'no-store' } });
    }
  });
}
