// Read the current test patient's state without exposing credentials to the browser.
import { GetCommand } from '@aws-sdk/lib-dynamodb';
import { database, patientId, table } from '../../../lib/aws';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function GET(request: Request) {
  if (new URL(request.url).searchParams.get('patient_id') !== patientId) {
    return Response.json({ error: 'Use the configured test patient.' }, { status: 400 });
  }
  try {
    const { Item } = await database.send(new GetCommand({
      TableName: table, Key: { patient_id: patientId }, ConsistentRead: true,
    }));
    return Response.json(Item ? { found: true, state: Item } : { found: false }, {
      headers: { 'Cache-Control': 'no-store' },
    });
  } catch (error) {
    console.error('RecoveryState read failed:', error instanceof Error ? error.name : 'UnknownError');
    return Response.json({ error: 'Could not read RecoveryState. Check the local server AWS credentials and permissions.' }, { status: 502 });
  }
}
