// Never proxy bridge errors/headers. Redact the service credential even in a
// malformed successful payload; only documented top-level fields reach callers.
function redact(value: unknown, key: string): unknown {
  if (typeof value === 'string') return value.split(key).join('[redacted]');
  if (Array.isArray(value)) return value.map(item => redact(item, key));
  if (value && typeof value === 'object') return Object.fromEntries(
    Object.entries(value).map(([name, item]) => [name.split(key).join('[redacted]'), redact(item, key)]),
  );
  return value;
}

export async function publicBridgePayload(response: Response, key: string, fields: readonly string[]) {
  if (!response.ok) throw new Error('Bridge request failed.');
  const payload: unknown = await response.json();
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) throw new Error('Invalid bridge response.');
  const object = payload as Record<string, unknown>;
  return redact(Object.fromEntries(fields.filter(name => Object.hasOwn(object, name)).map(name => [name, object[name]])), key);
}

export function protectedBridgeFetch(input: string | URL | Request, init?: RequestInit): Promise<Response> {
  return fetch(input, { ...init, cache: 'no-store', redirect: 'error', signal: init?.signal ?? AbortSignal.timeout(25_000) });
}
