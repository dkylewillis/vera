export const DEFAULT_ACTION_TIMEOUT_MS = 5 * 60 * 1000;

export type ActionCallOptions = { scope?: string; timeoutMs?: number };

export type SidecarCall = <T>(
  payload: Record<string, unknown>,
  label: string,
  requestId?: string,
  options?: ActionCallOptions,
) => Promise<T | null>;

export function sidecarCallWasCancelled(error?: string, cancelled?: boolean): boolean {
  if (cancelled) return true;
  return Boolean(error?.toLowerCase().includes('cancelled'));
}

export function sidecarTimeoutMessage(label: string, timeoutMs: number): string {
  return `${label} timed out after ${Math.round(timeoutMs / 1000)} seconds`;
}

export function sidecarCallScope(
  payload: Record<string, unknown>,
  label: string,
  options: ActionCallOptions = {},
): string {
  return options.scope || String(payload.action || label);
}
