// Validate the PDF on the Python bridge before S3 can start ingestion.
export type UploadValidation = { accepted: boolean; status: number; error?: string };
export const wrongDocumentMessage = 'Wrong document — not accepted. Please upload a hospital discharge letter.';

export async function validateUpload(
  bytes: Uint8Array,
  bridgeUrl: string,
  request: typeof fetch = fetch,
  requestId?: string,
): Promise<UploadValidation> {
  try {
    const response = await request(`${bridgeUrl}/documents/validate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/pdf', ...(requestId ? { 'X-Request-ID': requestId } : {}) },
      body: new Blob([new Uint8Array(bytes)], { type: 'application/pdf' }), cache: 'no-store',
    });
    const result = await response.json();
    if (response.ok && result.accepted === true) return { accepted: true, status: 200 };
    return {
      accepted: false, status: response.status === 422 ? 422 : 502,
      error: response.status === 422 ? result.error || wrongDocumentMessage
        : 'Could not check the document. Please try again.',
    };
  } catch {
    return { accepted: false, status: 502, error: 'Could not check the document. Please try again.' };
  }
}
