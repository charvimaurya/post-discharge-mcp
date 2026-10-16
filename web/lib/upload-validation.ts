// Validate the PDF on the Python bridge before S3 can start ingestion.
export type UploadValidation = { accepted: boolean; status: number; error?: string };
export const wrongDocumentMessage = 'Wrong document — not accepted. Please upload a hospital discharge letter.';

// The demo accepts PDF letters of at most 5 MB.
export const MAX_UPLOAD_BYTES = 5 * 1024 * 1024;
export const tooLargeMessage = 'That file is too large. Please upload a PDF under 5 MB.';
export const missingSessionMessage = 'This upload has no session. Please reload the demo page and try again.';
export const uploadLimitMessage = "You've reached the upload limit for this demo. Please try again later.";
export const UPLOADS_PER_SESSION = 3;

// Checks made before anything is sent to the bridge or S3. Null means the file may go on.
export function checkUploadFile(name: string, type: string, bytes: Uint8Array): { status: number; error: string } | null {
  if (!bytes.length) return { status: 400, error: 'Choose a PDF file.' };
  if (!name.toLowerCase().endsWith('.pdf') || (type && type !== 'application/pdf')) return { status: 400, error: wrongDocumentMessage };
  if (bytes.length > MAX_UPLOAD_BYTES) return { status: 413, error: tooLargeMessage };
  const start = Buffer.from(bytes.subarray(0, 1024));
  if (!start.includes(Buffer.from('%PDF-'))) return { status: 400, error: wrongDocumentMessage };
  return null;
}

// Counts letters stored per session, in this server's memory (a restart clears it). Each stored
// letter starts a Bedrock extraction, so only stored uploads count, not rejected files.
export function createUploadLimiter(limit = UPLOADS_PER_SESSION) {
  const stored = new Map<string, number>();
  return {
    canUpload: (sessionId: string) => (stored.get(sessionId) ?? 0) < limit,
    recordUpload: (sessionId: string) => { stored.set(sessionId, (stored.get(sessionId) ?? 0) + 1); },
  };
}

export async function validateUpload(
  bytes: Uint8Array,
  bridgeUrl: string,
  request: typeof fetch = fetch,
  requestId?: string,
  extraHeaders: Record<string, string> = {},
): Promise<UploadValidation> {
  try {
    const response = await request(`${bridgeUrl}/documents/validate`, {
      method: 'POST',
      headers: { ...extraHeaders, 'Content-Type': 'application/pdf', ...(requestId ? { 'X-Request-ID': requestId } : {}) },
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

// After the letter is stored: ask the bridge to delete what was recorded against the previous
// letter, so nothing from the old plan shows as done on the new one. True when it was cleared.
export async function clearPreviousHistory(
  bridgeUrl: string,
  request: typeof fetch = fetch,
  requestId?: string,
  extraHeaders: Record<string, string> = {},
): Promise<boolean> {
  try {
    const response = await request(`${bridgeUrl}/documents/uploaded`, {
      method: 'POST', headers: { ...extraHeaders, ...(requestId ? { 'X-Request-ID': requestId } : {}) }, cache: 'no-store',
    });
    return response.ok;
  } catch {
    return false;
  }
}
