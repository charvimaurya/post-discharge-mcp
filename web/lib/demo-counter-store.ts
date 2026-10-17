import { TransactWriteCommand } from '@aws-sdk/lib-dynamodb';
import type { Counter } from './demo-limits.ts';

export async function distributedConsume(
  rules: Counter[], table: string,
  send: (command: TransactWriteCommand) => Promise<unknown>,
): Promise<boolean> {
  try {
    await send(new TransactWriteCommand({ TransactItems: rules.map(rule => ({ Update: {
      TableName: table, Key: { counter_key: rule.key },
      UpdateExpression: 'SET expires_at = :expires ADD #count :one',
      ConditionExpression: 'attribute_not_exists(#count) OR #count < :limit',
      ExpressionAttributeNames: { '#count': 'request_count' },
      ExpressionAttributeValues: { ':expires': rule.expires, ':one': 1, ':limit': rule.limit },
    } })) }));
    return true;
  } catch (error) {
    // Only explicit quota condition failures are 429. IAM/throttle/outage/conflict
    // must fail closed as unavailable; never fall back to local counters.
    const value = error as { name?: string; CancellationReasons?: { Code?: string }[] };
    if (value.name === 'TransactionCanceledException' && value.CancellationReasons?.some(reason => reason.Code === 'ConditionalCheckFailed')) return false;
    throw new Error('Demo quota service unavailable.');
  }
}

