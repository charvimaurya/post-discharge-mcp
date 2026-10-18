import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { loadBindings, transform } from 'next/dist/build/swc/index.js';

const require = createRequire(import.meta.url);
await loadBindings();

async function route(name: string) {
  const calls: { path: string; init?: RequestInit }[] = [];
  const code = (await transform(readFileSync(new URL(`../app/api/${name}/route.ts`, import.meta.url), 'utf8'), {
    filename: 'route.ts', jsc: { parser: { syntax: 'typescript' } }, module: { type: 'commonjs' },
  })).code;
  const module = { exports: {} as Record<string, (request: Request) => Promise<Response>> };
  new Function('require', 'module', 'exports', code)((id: string) => {
    if (id.endsWith('/demo-guard')) return { withDemoLimits: (_: Request, __: string, handler: (session: string) => Promise<Response>) => handler('signed-session') };
    if (id.endsWith('/api-security')) return { checkRequestOrigin: () => null };
    if (id.endsWith('/bridge')) return { bridgeJson: async (path: string, _: string, __: string[], init?: RequestInit) => {
      calls.push({ path, init }); return { response: 'Saved', tasks: [], medications: [] };
    } };
    return require(`../lib/${id.split('/').at(-1)}.ts`);
  }, module, module.exports);
  return { handlers: module.exports, calls };
}

test('Next chat forwards the message and signed session, never a browser-selected patient', async () => {
  const { handlers, calls } = await route('chat');
  const response = await handlers.POST(new Request('http://localhost:3000/api/chat', { method: 'POST',
    body: JSON.stringify({ message: 'I completed my walk', session_id: 'forged-session' }) }));
  assert.equal(response.status, 200);
  assert.equal(response.headers.get('cache-control'), 'no-store');
  assert.deepEqual(JSON.parse(String(calls[0].init?.body)), { message: 'I completed my walk', session_id: 'signed-session' });
  const rejected = await handlers.POST(new Request('http://localhost:3000/api/chat', { method: 'POST',
    body: JSON.stringify({ message: 'I completed my walk', patient_id: 'another_patient' }) }));
  assert.equal(rejected.status, 400);
  assert.equal(calls.length, 1);
});

for (const name of ['today', 'week-summary']) test(`Next ${name} reads the bridge without caching or accepting a patient selector`, async () => {
  const { handlers, calls } = await route(name);
  assert.equal((await handlers.GET(new Request(`http://localhost:3000/api/${name}?patient_id=another_patient`))).status, 400);
  assert.equal(calls.length, 0);
  const response = await handlers.GET(new Request(`http://localhost:3000/api/${name}`));
  assert.equal(response.status, 200);
  assert.equal(response.headers.get('cache-control'), 'no-store');
  assert.equal(calls[0].path, `/${name}`);
});

test('task button forwards only its occurrence ID and rejects patient selectors', async () => {
  const { handlers, calls } = await route('tasks/complete');
  const request = (body: object) => new Request('http://localhost:3000/api/tasks/complete', {
    method: 'POST', body: JSON.stringify(body),
  });
  assert.equal((await handlers.POST(request({ occurrence_id: 'walk#2026-10-23#2' }))).status, 200);
  assert.equal(calls[0].path, '/tasks/complete');
  assert.deepEqual(JSON.parse(String(calls[0].init?.body)), { occurrence_id: 'walk#2026-10-23#2' });
  assert.equal((await handlers.POST(request({ occurrence_id: 'walk#2026-10-23#2', patient_id: 'other' }))).status, 400);
  assert.equal(calls.length, 1);
});

test('recovery-day forwards a validated date only and rejects browser patient selectors', async () => {
  const { handlers, calls } = await route('recovery-day');
  for (const query of ['', '?date=2026-02-30', '?date=2026-10-20&patient_id=other', '?date=2026-10-20&date=2026-10-21']) {
    assert.equal((await handlers.GET(new Request(`http://localhost:3000/api/recovery-day${query}`))).status, 400);
  }
  assert.equal(calls.length, 0);
  const response = await handlers.GET(new Request('http://localhost:3000/api/recovery-day?date=2026-10-20'));
  assert.equal(response.status, 200);
  assert.equal(response.headers.get('cache-control'), 'no-store');
  assert.equal(calls[0].path, '/recovery-day?date=2026-10-20');
});
