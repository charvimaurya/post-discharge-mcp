import { productionRuntime, type Environment } from './runtime-config.ts';

// No SDK/environment reads here; bridge.ts supplies the server-only loader.
export function createBridgeKeyProvider(
  load: (arn: string) => Promise<string>,
  environment: () => Environment,
  now: () => number = Date.now,
) {
  let cached: { arn: string; key: string; expires: number } | undefined;
  let pending: { arn: string; value: Promise<string> } | undefined;
  return async function getKey(): Promise<string> {
    const env = environment();
    if (!productionRuntime(env) && env.BRIDGE_KEY?.trim()) return env.BRIDGE_KEY.trim();
    const arn = env.BRIDGE_KEY_SECRET_ARN?.trim();
    if (!arn?.startsWith('arn:aws:secretsmanager:')) throw new Error('Bridge authentication is not configured.');
    if (cached?.arn === arn && cached.expires > now()) return cached.key;
    if (pending?.arn === arn) return pending.value;
    const value = (async () => {
      const key = (await load(arn)).trim();
      if (!/^[\x21-\x7e]{32,}$/.test(key)) throw new Error('Bridge authentication is not configured.');
      cached = { arn, key, expires: now() + 300_000 };
      return key;
    })();
    pending = { arn, value };
    try { return await value; }
    finally { if (pending?.value === value) pending = undefined; }
  };
}
