// Upload a PDF; the existing S3 notification starts asynchronous processing.
import { randomBytes } from 'node:crypto';
import { PutObjectCommand } from '@aws-sdk/client-s3';
import { bucket, patientId, s3 } from '../../../lib/aws';

export const runtime = 'nodejs';

export async function POST(request: Request) {
  let form: FormData;
  try { form = await request.formData(); }
  catch { return Response.json({ error: 'Expected a multipart PDF upload.' }, { status: 400 }); }
  const file = form.get('file');
  if (!(file instanceof File) || !file.size) {
    return Response.json({ error: 'Choose a PDF file.' }, { status: 400 });
  }
  if (!file.name.toLowerCase().endsWith('.pdf') || (file.type && file.type !== 'application/pdf')) {
    return Response.json({ error: 'Only PDF files are supported.' }, { status: 400 });
  }
  const bytes = Buffer.from(await file.arrayBuffer());
  if (!bytes.subarray(0, 1024).includes(Buffer.from('%PDF-'))) {
    return Response.json({ error: 'The file does not contain a PDF header.' }, { status: 400 });
  }
  const documentId = `ui_${randomBytes(8).toString('hex')}`;
  try {
    await s3.send(new PutObjectCommand({
      Bucket: bucket,
      Key: `patients/${patientId}/documents/${documentId}.pdf`,
      Body: bytes,
      ContentType: 'application/pdf',
    }));
    return Response.json({ patient_id: patientId, document_id: documentId, status: 'uploaded' });
  } catch (error) {
    console.error('S3 upload failed:', error instanceof Error ? error.name : 'UnknownError');
    return Response.json({ error: 'S3 upload failed. Check the local server AWS credentials and permissions.' }, { status: 502 });
  }
}
