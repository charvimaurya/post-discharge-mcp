// Server-only address of the local Python web bridge (scripts/run_web_bridge.py).
import 'server-only';

export const bridgeUrl = process.env.AGENT_API_URL || 'http://127.0.0.1:8002';

// Headers for every call to the bridge. BRIDGE_KEY is server-only: it is never
// prefixed with NEXT_PUBLIC_, so Next.js never sends it to the browser.
export const BRIDGE_KEY_HEADER = 'X-AfterWard-Key';

export function bridgeHeaders(extra: Record<string, string> = {}): Record<string, string> {
  const key = process.env.BRIDGE_KEY;
  return key ? { ...extra, [BRIDGE_KEY_HEADER]: key } : { ...extra };
}
