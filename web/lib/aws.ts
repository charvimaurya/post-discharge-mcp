// Server-only AWS clients for the existing document pipeline.
import 'server-only';
import { S3Client } from '@aws-sdk/client-s3';
import { DynamoDBClient } from '@aws-sdk/client-dynamodb';
import { DynamoDBDocumentClient } from '@aws-sdk/lib-dynamodb';
import { awsSettings } from './runtime-config';

// Resolve settings at request time, not while Amplify collects build metadata.
export function awsResources() {
  const { region, bucket, table, patientId } = awsSettings(process.env);
  return {
    bucket, table, patientId,
    s3: new S3Client({ region }),
    database: DynamoDBDocumentClient.from(new DynamoDBClient({ region })),
  };
}
