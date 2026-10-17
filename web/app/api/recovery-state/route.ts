import { withDemoLimits } from '../../../lib/demo-guard';
// Read the current test patient's state without exposing credentials to the browser.
import { GetCommand } from '@aws-sdk/lib-dynamodb';
import { awsResources } from '../../../lib/aws';
import { checkRequestOrigin } from '../../../lib/api-security';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

async function handleGET(request: Request, demoSession: string) {
  try {
    const { database, patientId, table } = awsResources();
    if (new URL(request.url).searchParams.get('patient_id') !== patientId) {
      return Response.json({ error: 'Use the configured test patient.' }, { status: 400 });
    }
    const { Item } = await database.send(new GetCommand({
      TableName: table, Key: { patient_id: patientId }, ConsistentRead: true,
    }));
    return Response.json(Item ? { found: true, state: Item } : { found: false }, {
      headers: { 'Cache-Control': 'no-store' },
    });
  } catch {
    console.error('RecoveryState read failed');
    return Response.json({ error: 'Could not load the recovery plan. Please try again.' }, { status: 502 });
  }
}

export async function GET(request: Request) {
  const rejected = checkRequestOrigin(request);
  if (rejected) return rejected;
  return withDemoLimits(request, 'read', session => handleGET(request, session));
}
