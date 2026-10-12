// One request ID from the browser's call to the last log line.
// The /api routes reuse an incoming X-Request-ID if it looks like an ID, or make one, send it to
// the Python bridge, and return it. The bridge, the agent and the MCP tools log it on every line.

const VALID = /^[A-Za-z0-9_-]{8,64}$/;

export const REQUEST_ID_HEADER = 'X-Request-ID';

// A header is untrusted text: only an ID-shaped value is reused.
export function requestIdFrom(headers: Headers, make: () => string = () => crypto.randomUUID().replace(/-/g, '')): string {
  const sent = headers.get(REQUEST_ID_HEADER);
  return sent && VALID.test(sent) ? sent : make();
}
