import { test } from 'node:test';
import assert from 'node:assert/strict';
import { localDemoLimitsDisabled } from '../lib/runtime-config.ts';

test('demo limit bypass requires explicit local development opt-in', () => {
  assert.equal(localDemoLimitsDisabled({ NODE_ENV: 'development', DISABLE_LOCAL_DEMO_LIMITS: 'true' }), true);
  for (const env of [
    { NODE_ENV: 'development' },
    { NODE_ENV: 'development', DISABLE_LOCAL_DEMO_LIMITS: 'false' },
    { NODE_ENV: 'production', DISABLE_LOCAL_DEMO_LIMITS: 'true' },
    { NODE_ENV: 'development', AFTERWARD_RUNTIME: 'amplify', DISABLE_LOCAL_DEMO_LIMITS: 'true' },
    { DISABLE_LOCAL_DEMO_LIMITS: 'true' },
  ]) assert.equal(localDemoLimitsDisabled(env), false);
});
