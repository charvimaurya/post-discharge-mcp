// Upload a PDF; the existing S3 notification starts asynchronous processing.
import { randomBytes } from 'node:crypto';
import { PutObjectCommand } from '@aws-sdk/client-s3';
import { bucket, patientId, s3 } from '../../../lib/aws';
import { bridgeUrl } from '../../../lib/bridge';
import { REQUEST_ID_HEADER, requestIdFrom } from '../../../lib/request-id';
import { clearPreviousHistory, validateUpload, wrongDocumentMessage } from '../../../lib/upload-validation';

export const runtime = 'nodejs';

export async function POST(request: Request) {
  const requestId = requestIdFrom(request.headers);
  let form: FormData;
  try { form = await request.formData(); }
  catch { return Response.json({ error: 'Expected a multipart PDF upload.' }, { status: 400 }); }
  const file = form.get('file');
  if (!(file instanceof File) || !file.size) {
    return Response.json({ error: 'Choose a PDF file.' }, { status: 400 });
  }
  if (!file.name.toLowerCase().endsWith('.pdf') || (file.type && file.type !== 'application/pdf')) {
    return Response.json({ error: wrongDocumentMessage }, { status: 400 });
  }
  const bytes = Buffer.from(await file.arrayBuffer());
  if (!bytes.subarray(0, 1024).includes(Buffer.from('%PDF-'))) {
    return Response.json({ error: wrongDocumentMessage }, { status: 400 });
  }
  const validation = await validateUpload(bytes, bridgeUrl, fetch, requestId);
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
  // The new letter replaces the plan, so what was recorded against the old one is deleted. Done
  // only once the letter is safely stored; if it fails, the upload itself has still succeeded.
  const historyCleared = await clearPreviousHistory(bridgeUrl, fetch, requestId);
  if (!historyCleared) console.error('Previous history was not cleared after upload', requestId);
  return Response.json({ patient_id: patientId, document_id: documentId, status: 'uploaded', history_cleared: historyCleared },
    { headers: { [REQUEST_ID_HEADER]: requestId } });
}
