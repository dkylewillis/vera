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
