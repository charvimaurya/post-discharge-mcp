// Server-only address of the local Python web bridge (scripts/run_web_bridge.py).
import 'server-only';

export const bridgeUrl = process.env.AGENT_API_URL || 'http://127.0.0.1:8002';
