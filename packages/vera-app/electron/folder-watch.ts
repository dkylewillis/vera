/** Watcher helpers for managed libraries. `.vera/` writes must not sync again. */

export const LIBRARY_SYNC_INTERVAL_MS = 10 * 60 * 1000;

export function isManagedLibraryEvent(filename: string | Buffer | null | undefined): boolean {
  if (filename == null || filename === '') return false;
  const text = typeof filename === 'string' ? filename : filename.toString('utf8');
  const normalized = text.replace(/\\/g, '/');
  return normalized === '.vera' || normalized.startsWith('.vera/');
}

export function librarySyncDecision(
  report: { managed?: boolean; needs_confirmation?: boolean } | null | undefined,
  confirmed: boolean,
): 'skip' | 'confirm' | 'done' {
  if (!report || report.managed === false) return 'skip';
  if (report.needs_confirmation && !confirmed) return 'confirm';
  return 'done';
}

export function librarySyncWasCancelled(report: unknown): boolean {
  if (!report || typeof report !== 'object') return false;
  const record = report as { cancelled?: boolean; error?: string };
  if (record.cancelled) return true;
  return typeof record.error === 'string' && /cancelled/i.test(record.error);
}

export interface LibrarySyncClaim<T> {
  requestId: string;
  run: Promise<T>;
}

/** Lets Stop cancel a sync that Convert is still waiting to start. */
export interface LibrarySyncAbort {
  aborted: Set<string>;
  onWait?: (activeRequestId: string, waiterId: string) => void;
  onWaitEnd?: (activeRequestId: string, waiterId: string) => void;
}

/**
 * One sync per library. A background sync skips a library that is already
 * syncing. A sync the user asked for (it has a `requestId`) waits for that
 * library only, then runs its own pass. A cancelled sync is not followed by
 * another pass.
 */
function librarySyncStoppedReport<R extends LibrarySyncClaim<unknown>>(): Awaited<R['run']> {
  return { cancelled: true, ok: false, error: 'Library sync cancelled' } as Awaited<R['run']>;
}

export async function claimLibrarySync<R extends LibrarySyncClaim<unknown>>(
  syncing: Map<string, R>,
  key: string,
  requestId: string | undefined,
  start: (requestId: string) => R,
  newRequestId: () => string,
  abort?: LibrarySyncAbort,
): Promise<Awaited<R['run']> | null> {
  if (requestId && abort?.aborted.has(requestId)) {
    abort.aborted.delete(requestId);
    return librarySyncStoppedReport<R>();
  }
  if (!requestId && syncing.has(key)) return null;

  if (requestId) {
    let running = syncing.get(key);
    const seen = new Set<R>();
    while (running && !seen.has(running)) {
      seen.add(running);
      abort?.onWait?.(running.requestId, requestId);
      const report = await running.run.catch(() => null);
      abort?.onWaitEnd?.(running.requestId, requestId);
      if (abort?.aborted.has(requestId)) {
        abort.aborted.delete(requestId);
        return librarySyncStoppedReport<R>();
      }
      if (librarySyncWasCancelled(report)) return report as Awaited<R['run']>;
      running = syncing.get(key);
    }
  }

  const record = start(requestId ?? newRequestId());
  syncing.set(key, record);
  try {
    return await record.run as Awaited<R['run']>;
  } finally {
    if (syncing.get(key) === record) syncing.delete(key);
  }
}
