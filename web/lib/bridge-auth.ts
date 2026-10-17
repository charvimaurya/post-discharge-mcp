// Pure header construction; only server-only bridge.ts supplies the secret.
export function authenticatedBridgeHeaders(key: string | undefined, requestId?: string): Record<string, string> {
  if (!key?.trim()) throw new Error('Bridge authentication is not configured.');
  return { 'X-Bridge-Key': key.trim(), ...(requestId ? { 'X-Request-ID': requestId } : {}) };
}
