// Pure validation shared by the server runtime and the Amplify env writer.
export type Environment = Record<string, string | undefined>;
export function productionRuntime(env: Environment): boolean {
  return env.NODE_ENV === 'production' || env.AFTERWARD_RUNTIME === 'amplify';
}

export function bridgeEndpoint(env: Environment): string {
  const raw = env.AGENT_API_URL || (productionRuntime(env) ? '' : 'http://127.0.0.1:8002');
  let url: URL;
  try { url = new URL(raw); } catch { throw new Error('Bridge endpoint is not configured.'); }
  const local = ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname);
  if ((url.protocol !== 'https:' && !(url.protocol === 'http:' && local && !productionRuntime(env)))
      || url.username || url.password || url.search || url.hash || url.pathname !== '/') {
    throw new Error('Bridge endpoint must be a trusted HTTPS origin.');
  }
  return url.origin;
}

export function awsSettings(env: Environment) {
  const production = productionRuntime(env);
  const bucket = env.DOCUMENT_BUCKET?.trim() || '';
  const table = env.RECOVERY_STATE_TABLE || (production ? '' : 'PostDischargeRecoveryState');
  const patientId = env.TEST_PATIENT_ID || (production ? '' : 'demo_patient_001');
  const region = env.AFTERWARD_AWS_REGION || env.AWS_REGION || (production ? '' : 'eu-west-2');
  if (!bucket || !table || !patientId || !region) throw new Error('AWS runtime settings are not configured.');
  return { bucket, table, patientId, region };
}

export function canonicalOrigin(env: Environment): string | undefined {
  if (!env.APP_ORIGIN && !productionRuntime(env)) return undefined;
  let url: URL;
  try { url = new URL(env.APP_ORIGIN || ''); } catch { throw new Error('Application origin is not configured.'); }
  if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash || url.pathname !== '/') {
    throw new Error('Application origin must be an HTTPS origin.');
  }
  return url.origin;
}
