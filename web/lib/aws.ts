// Server-only AWS clients for the existing document pipeline.
import 'server-only';
import { S3Client } from '@aws-sdk/client-s3';
import { DynamoDBClient } from '@aws-sdk/client-dynamodb';
import { DynamoDBDocumentClient } from '@aws-sdk/lib-dynamodb';

const region = process.env.AWS_REGION || 'eu-west-2';
export const bucket = process.env.DOCUMENT_BUCKET || 'afterward-documents-992617582533-london';
export const table = process.env.RECOVERY_STATE_TABLE || 'PostDischargeRecoveryState';
export const patientId = process.env.TEST_PATIENT_ID || 'demo_patient_001';
export const s3 = new S3Client({ region });
export const database = DynamoDBDocumentClient.from(new DynamoDBClient({ region }));
