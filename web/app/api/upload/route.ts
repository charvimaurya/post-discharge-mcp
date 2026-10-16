// Upload a PDF; the existing S3 notification starts asynchronous processing.
import { randomBytes } from 'node:crypto';
import { PutObjectCommand } from '@aws-sdk/client-s3';
import { documentBucket, missingBucketMessage, patientId, s3 } from '../../../lib/aws';
import { bridgeHeaders, bridgeUrl } from '../../../lib/bridge';
import { REQUEST_ID_HEADER, requestIdFrom } from '../../../lib/request-id';
import {
  MAX_UPLOAD_BYTES, checkUploadFile, clearPreviousHistory, createUploadLimiter, missingSessionMessage, tooLargeMessage,
  uploadLimitMessage, validateUpload,
} from '../../../lib/upload-validation';

export const runtime = 'nodejs';

// Demo limit: 3 stored letters per browser session, kept in this server's memory.
const uploads = createUploadLimiter();

export async function POST(request: Request) {
  const requestId = requestIdFrom(request.headers);
  // Checked first, before anything is sent to the bridge or S3.
  let bucket: string;
  try { bucket = documentBucket(); }
  catch {
    console.error('Upload refused: DOCUMENT_BUCKET is not set', requestId);
    return Response.json({ error: missingBucketMessage }, { status: 500 });
  }
  let form: FormData;
  try { form = await request.formData(); }
  catch { return Response.json({ error: 'Expected a multipart PDF upload.' }, { status: 400 }); }
  const sessionValue = form.get('session_id');
  const sessionId = typeof sessionValue === 'string' ? sessionValue.trim() : '';
  if (!sessionId) return Response.json({ error: missingSessionMessage }, { status: 400 });
  if (!uploads.canUpload(sessionId)) return Response.json({ error: uploadLimitMessage }, { status: 429 });
  const file = form.get('file');
  if (!(file instanceof File) || !file.size) {
    return Response.json({ error: 'Choose a PDF file.' }, { status: 400 });
  }
  // Too large: refused before the bytes are copied or sent anywhere.
  if (file.size > MAX_UPLOAD_BYTES) return Response.json({ error: tooLargeMessage }, { status: 413 });
  const bytes = Buffer.from(await file.arrayBuffer());
  const problem = checkUploadFile(file.name, file.type, bytes);
  if (problem) return Response.json({ error: problem.error }, { status: problem.status });
  const validation = await validateUpload(bytes, bridgeUrl, fetch, requestId, bridgeHeaders());
  if (!validation.accepted) {
    return Response.json({ error: validation.error }, { status: validation.status });
  }
  const documentId = `ui_${randomBytes(8).toString('hex')}`;
  try {
    await s3.send(new PutObjectCommand({
      Bucket: bucket,
      Key: `patients/${patientId}/documents/${documentId}.pdf`,
      Body: bytes,
      ContentType: 'application/pdf',
    }));
  } catch (error) {
    console.error('S3 upload failed:', error instanceof Error ? error.name : 'UnknownError', requestId);
    return Response.json({ error: 'S3 upload failed. Check the local server AWS credentials and permissions.' }, { status: 502 });
  }
  uploads.recordUpload(sessionId);
  // The new letter replaces the plan, so what was recorded against the old one is deleted. Done
  // only once the letter is safely stored; if it fails, the upload itself has still succeeded.
  const historyCleared = await clearPreviousHistory(bridgeUrl, fetch, requestId, bridgeHeaders());
  if (!historyCleared) console.error('Previous history was not cleared after upload', requestId);
  return Response.json({ patient_id: patientId, document_id: documentId, status: 'uploaded', history_cleared: historyCleared },
    { headers: { [REQUEST_ID_HEADER]: requestId } });
}
