import { boundedRequest } from '../../../lib/demo-limits';
import { withDemoLimits } from '../../../lib/demo-guard';
// Upload a PDF; the existing S3 notification starts asynchronous processing.
import { randomBytes } from 'node:crypto';
import { PutObjectCommand } from '@aws-sdk/client-s3';
import { awsResources } from '../../../lib/aws';
import { bridgeHeaders, bridgeUrl } from '../../../lib/bridge';
import { protectedBridgeFetch } from '../../../lib/bridge-response';
import { checkRequestOrigin } from '../../../lib/api-security';
import { REQUEST_ID_HEADER, requestIdFrom } from '../../../lib/request-id';
import { clearPreviousHistory, validateUpload, wrongDocumentMessage } from '../../../lib/upload-validation';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const MAX_PDF_BYTES = 4 * 1024 * 1024;

async function handlePOST(request: Request, demoSession: string) {
  const requestId = requestIdFrom(request.headers);
  if (Number(request.headers.get('Content-Length')) > MAX_PDF_BYTES + 65536) {
    return Response.json({ error: 'Choose a PDF smaller than 4 MiB.' }, { status: 413 });
  }
  let form: FormData;
  try { form = await (await boundedRequest(request, MAX_PDF_BYTES + 65536)).formData(); }
  catch (error) { return Response.json({ error: error instanceof RangeError ? 'Choose a PDF smaller than 4 MiB.' : 'Expected a multipart PDF upload.' }, { status: error instanceof RangeError ? 413 : 400 }); }
  const file = form.get('file');
  if (!(file instanceof File) || !file.size) {
    return Response.json({ error: 'Choose a PDF file.' }, { status: 400 });
  }
  if (file.size > MAX_PDF_BYTES) {
    return Response.json({ error: 'Choose a PDF smaller than 4 MiB.' }, { status: 413 });
  }
  if (!file.name.toLowerCase().endsWith('.pdf') || (file.type && file.type !== 'application/pdf')) {
    return Response.json({ error: wrongDocumentMessage }, { status: 400 });
  }
  const bytes = Buffer.from(await file.arrayBuffer());
  if (!bytes.subarray(0, 1024).includes(Buffer.from('%PDF-'))) {
    return Response.json({ error: wrongDocumentMessage }, { status: 400 });
  }
  let authHeaders: Record<string, string>;
  let endpoint: string;
  let resources: ReturnType<typeof awsResources>;
  try {
    endpoint = bridgeUrl();
    authHeaders = await bridgeHeaders(requestId);
    resources = awsResources();
  } catch { return Response.json({ error: 'Upload service is unavailable.' }, { status: 503 }); }
  const { bucket, patientId, s3 } = resources;
  const validation = await validateUpload(bytes, endpoint, protectedBridgeFetch, requestId, authHeaders);
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
  } catch {
    console.error('S3 upload failed', requestId);
    return Response.json({ error: 'Could not upload the document. Please try again.' }, { status: 502 });
  }
  // The new letter replaces the plan, so what was recorded against the old one is deleted. Done
  // only once the letter is safely stored; if it fails, the upload itself has still succeeded.
  const historyCleared = await clearPreviousHistory(endpoint, protectedBridgeFetch, requestId, authHeaders);
  if (!historyCleared) console.error('Previous history was not cleared after upload', requestId);
  return Response.json({ patient_id: patientId, document_id: documentId, status: 'uploaded', history_cleared: historyCleared },
    { headers: { 'Cache-Control': 'no-store', [REQUEST_ID_HEADER]: requestId } });
}

export async function POST(request: Request) {
  const rejected = checkRequestOrigin(request);
  if (rejected) return rejected;
  return withDemoLimits(request, 'upload', session => handlePOST(request, session));
}
