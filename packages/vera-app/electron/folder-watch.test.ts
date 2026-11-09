import { describe, expect, it } from 'vitest';

import { claimLibrarySync, isManagedLibraryEvent, librarySyncDecision, type LibrarySyncClaim } from './folder-watch.js';

describe('isManagedLibraryEvent', () => {
  it('ignores writes inside the managed library folder', () => {
    expect(isManagedLibraryEvent('.vera')).toBe(true);
    expect(isManagedLibraryEvent('.vera\\archives\\Plans\\Site Plan.pdf.vera')).toBe(true);
    expect(isManagedLibraryEvent('.vera/index/current.json')).toBe(true);
  });

  it('keeps source-document changes', () => {
    expect(isManagedLibraryEvent(null)).toBe(false);
    expect(isManagedLibraryEvent('Plans\\Site Plan.pdf')).toBe(false);
    expect(isManagedLibraryEvent('notes.md')).toBe(false);
  });
});

describe('librarySyncDecision', () => {
  it('asks before a mass delete and skips folders that are not libraries', () => {
    expect(librarySyncDecision({ managed: false }, false)).toBe('skip');
    expect(librarySyncDecision(null, false)).toBe('skip');
    expect(librarySyncDecision({ managed: true, needs_confirmation: true }, false)).toBe('confirm');
    expect(librarySyncDecision({ managed: true, needs_confirmation: true }, true)).toBe('done');
    expect(librarySyncDecision({ managed: true, needs_confirmation: false }, false)).toBe('done');
  });
});

describe('claimLibrarySync', () => {
  function deferred<T>(): { promise: Promise<T>; resolve: (value: T) => void } {
    let resolve: (value: T) => void = () => undefined;
    const promise = new Promise<T>((done) => { resolve = done; });
    return { promise, resolve };
  }

  it('skips a background sync while that library is already syncing and still syncs another library', async () => {
    const syncing = new Map<string, LibrarySyncClaim<{ ok: boolean }>>();
    const first = deferred<{ ok: boolean }>();
    const started: string[] = [];
    const running = claimLibrarySync(
      syncing,
      'lib-a',
      undefined,
      (requestId) => {
        started.push(requestId);
        return { requestId, run: first.promise };
      },
      () => 'bg-a',
    );
    const skipped = await claimLibrarySync(
      syncing,
      'lib-a',
      undefined,
      () => { throw new Error('should not start'); },
      () => 'bg-a-2',
    );
    const other = await claimLibrarySync(
      syncing,
      'lib-b',
      undefined,
      (requestId) => ({ requestId, run: Promise.resolve({ ok: true }) }),
      () => 'bg-b',
    );

    expect(skipped).toBeNull();
    expect(other).toEqual({ ok: true });
    expect(started).toEqual(['bg-a']);
    first.resolve({ ok: true });
    await running;
    expect(syncing.size).toBe(0);
  });

  it('waits only for the same library, then runs the user pass', async () => {
    const syncing = new Map<string, LibrarySyncClaim<{ ok: boolean }>>();
    const background = deferred<{ ok: boolean }>();
    const other = deferred<{ ok: boolean }>();
    const backgroundRun = claimLibrarySync(
      syncing,
      'lib-a',
      undefined,
      () => ({ requestId: 'bg-a', run: background.promise }),
      () => 'bg-a',
    );
    const otherRun = claimLibrarySync(
      syncing,
      'lib-b',
      undefined,
      () => ({ requestId: 'bg-b', run: other.promise }),
      () => 'bg-b',
    );
    const started: string[] = [];
    const user = claimLibrarySync(
      syncing,
      'lib-a',
      'user-1',
      (requestId) => {
        started.push(requestId);
        return { requestId, run: Promise.resolve({ ok: true }) };
      },
      () => 'generated',
    );
    await Promise.resolve();
    expect(started).toEqual([]);
    background.resolve({ ok: true });
    await expect(user).resolves.toEqual({ ok: true });
    expect(started).toEqual(['user-1']);
    other.resolve({ ok: true });
    await Promise.all([backgroundRun, otherRun]);
  });

  it('does not start a follow-up when Stop arrives while Convert is waiting', async () => {
    const syncing = new Map<string, LibrarySyncClaim<{ ok?: boolean; cancelled?: boolean }>>();
    const background = deferred<{ ok?: boolean; cancelled?: boolean }>();
    const waited: string[] = [];
    const abort = {
      aborted: new Set<string>(),
      onWait(activeRequestId: string, waiterId: string) {
        waited.push(`${activeRequestId}:${waiterId}`);
      },
    };
    const backgroundRun = claimLibrarySync(
      syncing,
      'lib-a',
      undefined,
      () => ({ requestId: 'bg-a', run: background.promise }),
      () => 'bg-a',
      abort,
    );
    const started: string[] = [];
    const user = claimLibrarySync(
      syncing,
      'lib-a',
      'user-1',
      (requestId) => {
        started.push(requestId);
        return { requestId, run: Promise.resolve({ ok: true }) };
      },
      () => 'generated',
      abort,
    );
    await Promise.resolve();
    expect(waited).toEqual(['bg-a:user-1']);
    abort.aborted.add('user-1');
    background.resolve({ ok: true });
    await expect(user).resolves.toMatchObject({ cancelled: true });
    expect(started).toEqual([]);
    await backgroundRun;
  });

  it('does not follow a cancelled sync with another pass', async () => {
    const syncing = new Map<string, LibrarySyncClaim<{ cancelled?: boolean }>>();
    const background = deferred<{ cancelled?: boolean }>();
    const backgroundRun = claimLibrarySync(
      syncing,
      'lib-a',
      undefined,
      () => ({ requestId: 'bg-a', run: background.promise }),
      () => 'bg-a',
    );
    const started: string[] = [];
    const user = claimLibrarySync(
      syncing,
      'lib-a',
      'user-1',
      (requestId) => {
        started.push(requestId);
        return { requestId, run: Promise.resolve({}) };
      },
      () => 'generated',
    );
    background.resolve({ cancelled: true });
    await expect(user).resolves.toEqual({ cancelled: true });
    expect(started).toEqual([]);
    await backgroundRun;
  });
});
