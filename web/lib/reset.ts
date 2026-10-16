// Ask the Python bridge to reset the demo patient and forget this session's conversation.
// Only the session_id is sent; the bridge decides which patient is reset.
export type ResetResult = { ok: boolean; status: number; error?: string };

export async function resetDemo(
  bridgeUrl: string,
  request: typeof fetch = fetch,
  requestId?: string,
  sessionId?: string,
  extraHeaders: Record<string, string> = {},
): Promise<ResetResult> {
  try {
    const response = await request(`${bridgeUrl}/reset`, {
      method: 'POST',
      headers: { ...extraHeaders, 'Content-Type': 'application/json', ...(requestId ? { 'X-Request-ID': requestId } : {}) },
      body: JSON.stringify({ session_id: sessionId }),
      cache: 'no-store',
    });
    if (response.ok) return { ok: true, status: 200 };
    const result = await response.json().catch(() => ({}));
    return { ok: false, status: response.status, error: result.error || 'Could not reset the demo. Please try again.' };
  } catch {
    return { ok: false, status: 502, error: 'Could not reach the AfterWard service.' };
  }
}
