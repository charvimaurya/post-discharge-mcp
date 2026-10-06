// Poll serially for this upload, ignoring any older ready document.
export type RecoveryState = Record<string, unknown>;
export type StateResponse = { found: boolean; state?: RecoveryState };
export const timeoutMessage = 'Processing timed out. Check Lambda/CloudWatch logs.';

export async function waitForRecoveryState(
  documentId: string,
  read: (signal: AbortSignal) => Promise<StateResponse>,
  signal: AbortSignal,
  timeoutMs = 90_000,
  intervalMs = 2_000,
): Promise<RecoveryState> {
  const deadline = AbortSignal.timeout(timeoutMs);
  const combined = AbortSignal.any([signal, deadline]);
  try {
    while (true) {
      combined.throwIfAborted();
      const result = await read(combined);
      combined.throwIfAborted();
      if (result.found && result.state?.document_id === documentId) {
        if (result.state.ingestion_status === 'ready') return result.state;
        if (['failed', 'error'].includes(String(result.state.ingestion_status))) {
          throw new Error('Document processing failed. Check Lambda/CloudWatch logs.');
        }
      }
      await new Promise<void>((resolve, reject) => {
        const abort = () => { clearTimeout(timer); reject(combined.reason); };
        const timer = setTimeout(() => {
          combined.removeEventListener('abort', abort);
          resolve();
        }, intervalMs);
        combined.addEventListener('abort', abort, { once: true });
      });
    }
  } catch (error) {
    if (deadline.aborted && !signal.aborted) throw new Error(timeoutMessage);
    throw error;
  }
}
