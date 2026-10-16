// The visitor's IP address, for the bridge's per-IP demo chat limit.
//
// Never the first x-forwarded-for value: the visitor can send that header themselves,
// and each proxy only appends. Trusted, in order:
//   1. CloudFront-Viewer-Address, set by CloudFront itself ("ip:port"), when present;
//   2. the last x-forwarded-for entry, the address our own proxy added;
//   3. x-real-ip.
// Returns null when none is present (local development), so the bridge uses its peer address.
type HeaderReader = { get(name: string): string | null };

function withoutPort(address: string): string {
  const value = address.trim();
  const bracketed = /^\[([^\]]+)\](?::\d+)?$/.exec(value);
  if (bracketed) return bracketed[1];
  const colons = value.split(':').length - 1;
  // IPv4 "a.b.c.d:port" has one colon; CloudFront writes IPv6 as "address:port".
  if (colons >= 1 && /:\d+$/.test(value) && (colons === 1 || colons > 2)) return value.replace(/:\d+$/, '');
  return value;
}

export function clientIp(headers: HeaderReader): string | null {
  const viewer = headers.get('cloudfront-viewer-address');
  if (viewer && viewer.trim()) return withoutPort(viewer);

  const forwarded = (headers.get('x-forwarded-for') || '').split(',').map(part => part.trim()).filter(Boolean);
  if (forwarded.length) return forwarded[forwarded.length - 1];

  const real = headers.get('x-real-ip');
  return real && real.trim() ? real.trim() : null;
}
