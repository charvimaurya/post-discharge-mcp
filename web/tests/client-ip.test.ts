import { test } from 'node:test';
import assert from 'node:assert/strict';
import { clientIp } from '../lib/client-ip.ts';

const headers = (values: Record<string, string>) => new Headers(values);

test('uses the address our proxy added (the last x-forwarded-for entry), not the first', () => {
  assert.equal(clientIp(headers({ 'x-forwarded-for': '1.2.3.4, 203.0.113.9' })), '203.0.113.9');
});

test('a fake first x-forwarded-for value cannot change the visitor IP, so it cannot bypass the IP limit', () => {
  const seen = new Set<string | null>();
  for (let n = 0; n < 50; n += 1) {
    seen.add(clientIp(headers({ 'x-forwarded-for': `10.0.0.${n}, 203.0.113.9` })));
  }
  assert.deepEqual([...seen], ['203.0.113.9']);
});

test("CloudFront's viewer address wins when present, without its port", () => {
  assert.equal(clientIp(headers({ 'cloudfront-viewer-address': '198.51.100.10:46532', 'x-forwarded-for': '1.2.3.4, 130.176.0.1' })), '198.51.100.10');
  assert.equal(clientIp(headers({ 'cloudfront-viewer-address': '2001:db8::1:46532' })), '2001:db8::1');
});

test('falls back to x-real-ip, then to nothing', () => {
  assert.equal(clientIp(headers({ 'x-real-ip': '192.0.2.5' })), '192.0.2.5');
  assert.equal(clientIp(headers({})), null);
});
