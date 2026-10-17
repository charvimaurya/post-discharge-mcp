import { createHmac, randomBytes, timingSafeEqual } from 'node:crypto';
import { isIP } from 'node:net';

export type DemoAction = 'chat' | 'upload' | 'read' | 'reminder' | 'reset';
export type Counter = { key: string; limit: number; expires: number };
const SESSION_SECONDS = 86400;
const COOKIE = 'afterward-demo';
function digest(key: string, value: string) { return createHmac('sha256', key).update(`afterward-demo-v1:${value}`).digest('hex'); }

export function demoIdentity(request: Request, key: string, now: number, secure: boolean) {
  const raw = request.headers.get('cookie')?.split(';').map(s => s.trim()).find(s => s.startsWith(`${COOKIE}=`))?.slice(COOKIE.length + 1) || '';
  const parts = raw.split('.');
  const payload = `${parts[0]}.${parts[1]}`;
  const expected = digest(key, `cookie:${payload}`);
  const valid = parts.length === 3 && /^[a-f0-9]{48}$/.test(parts[0]) && /^\d{10}$/.test(parts[1])
    && Number(parts[1]) > now && Number(parts[1]) <= now + SESSION_SECONDS
    && /^[a-f0-9]{64}$/.test(parts[2])
    && timingSafeEqual(Buffer.from(expected), Buffer.from(parts[2]));
  const id = valid ? parts[0] : randomBytes(24).toString('hex');
  const expires = valid ? Number(parts[1]) : now + SESSION_SECONDS;
  const token = `${id}.${expires}.${digest(key, `cookie:${id}.${expires}`)}`;
  return { session: id, expires, cookie: `${COOKIE}=${token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${expires - now}${secure ? '; Secure' : ''}` };
}

// Only use behind a proxy that appends the real peer address. Never use the
// leftmost XFF element: viewers can supply it. Hops must match the deployed chain.
export function clientAddress(request: Request, production: boolean, hops?: string): string {
  if (!production) return 'local-development';
  if (!hops || !/^[1-5]$/.test(hops)) throw new Error('Trusted proxy chain is not configured.');
  const chain = (request.headers.get('x-forwarded-for') || '').split(',').map(s => s.trim());
  const candidate = chain.at(-Number(hops)) || '';
  if (!isIP(candidate)) throw new Error('Trusted client address is unavailable.');
  // Normalize IPv6 spelling so equivalent addresses share a counter.
  return isIP(candidate) === 6 ? new URL(`http://[${candidate}]`).hostname : candidate;
}

export function demoCounters(action: DemoAction, session: string, sessionExpires: number, ip: string, key: string, now: number): Counter[] {
  const hour = Math.floor(now / 3600);
  const minute = Math.floor(now / 60);
  const who = digest(key, `ip:${ip}`);
  const counter = (name: string, limit: number, expires: number): Counter => ({ key: name, limit, expires });
  if (action === 'chat') return [counter(`chat:s:${session}:${hour}`, 30, (hour + 1) * 3600), counter(`chat:ip:${who}:${hour}`, 100, (hour + 1) * 3600)];
  if (action === 'upload') return [
    counter(`upload:s:${session}`, 3, sessionExpires),
    counter(`upload:ip:${who}:${hour}`, 10, (hour + 1) * 3600),
    counter(`reset:s:${session}:${hour}`, 3, (hour + 1) * 3600),
    counter(`reset:ip:${who}:${hour}`, 10, (hour + 1) * 3600),
  ];
  if (action === 'reset') return [counter(`reset:s:${session}:${hour}`, 3, (hour + 1) * 3600), counter(`reset:ip:${who}:${hour}`, 10, (hour + 1) * 3600)];
  const period = action === 'read' ? minute : hour;
  const expiry = action === 'read' ? (minute + 1) * 60 : (hour + 1) * 3600;
  return [counter(`${action}:s:${session}:${period}`, action === 'read' ? 60 : 60, expiry),
    counter(`${action}:ip:${who}:${period}`, action === 'read' ? 300 : 200, expiry)];
}

// One-process local development only. Cloud instances must use atomic shared storage.
export function memoryCounters() {
  const counts = new Map<string, { count: number; expires: number }>();
  return async (rules: Counter[], now: number) => {
    for (const [key, item] of counts) if (item.expires <= now) counts.delete(key);
    if (rules.some(rule => (counts.get(rule.key)?.count || 0) >= rule.limit)) return false;
    for (const rule of rules) counts.set(rule.key, { count: (counts.get(rule.key)?.count || 0) + 1, expires: rule.expires });
    return true;
  };
}

export async function boundedRequest(request: Request, limit: number): Promise<Request> {
  if (Number(request.headers.get('content-length')) > limit) throw new RangeError('Request too large');
  if (!request.body) return request;
  const reader = request.body.getReader(); const chunks: Uint8Array[] = []; let length = 0;
  try {
    while (true) {
      const next = await reader.read(); if (next.done) break;
      length += next.value.byteLength;
      if (length > limit) { await reader.cancel(); throw new RangeError('Request too large'); }
      chunks.push(next.value);
    }
  } finally { reader.releaseLock(); }
  return new Request(request.url, { method: request.method, headers: request.headers, body: Buffer.concat(chunks) });
}
