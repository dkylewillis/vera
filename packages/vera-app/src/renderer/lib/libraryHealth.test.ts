import { describe, expect, it } from 'vitest';

import { libraryActivityLabel, libraryHealth, nextSyncReport, type LibraryHealthInput } from './libraryHealth';
import type { LibrarySyncReport } from '../types';

function input(overrides: Partial<LibraryHealthInput> = {}): LibraryHealthInput {
  return {
    libraryPath: 'C:\\library',
    pendingCount: 0,
    index: { exists: true, fresh: true, reasons: [] },
    ...overrides,
  };
}

describe('libraryHealth', () => {
  it('prefers working, then attention, then pending, then setup, then ready', () => {
    const failures: LibrarySyncReport = {
      ok: false,
      failed: 1,
      errors: [{ input: 'a.pdf', error: 'bad' }],
    };
    expect(libraryHealth(input({
      syncing: true,
      syncReport: failures,
      pendingCount: 3,
      index: { exists: false, fresh: false, reasons: [] },
    })).state).toBe('working');
    expect(libraryHealth(input({ syncReport: failures, pendingCount: 3 })).state).toBe('attention');
    expect(libraryHealth(input({ pendingCount: 2 })).state).toBe('pending');
    expect(libraryHealth(input({
      pendingCount: 0,
      index: { exists: true, fresh: false, reasons: ['changed'] },
    })).state).toBe('pending');
    expect(libraryHealth(input({ index: { exists: false, fresh: false, reasons: [] } })).state).toBe('setup');
    expect(libraryHealth(input()).state).toBe('ready');
  });

  it('treats a stale index alone as pending, not attention', () => {
    const health = libraryHealth(input({
      index: { exists: true, fresh: false, reasons: ['mtime changed'] },
    }));
    expect(health.state).toBe('pending');
    expect(health.label).toBe('Out of date');
    expect(health.title).toBe('Index needs updating: mtime changed');
    expect(health.items.find((item) => item.kind === 'index')?.actions).toEqual(['updateIndex']);
  });

  it('treats a failed sync with only an error string as attention', () => {
    const health = libraryHealth(input({
      syncReport: { ok: false, error: 'Library sync failed' },
    }));
    expect(health.state).toBe('attention');
    expect(health.label).toBe('Needs attention (1)');
    const problem = health.items.find((item) => item.kind === 'syncError');
    expect(problem?.text).toBe('Library sync failed');
    expect(problem?.actions).toEqual(['tryAgain', 'openConvertLog']);
  });

  it('joins failure paths to the library root and summarizes past 20', () => {
    const errors = Array.from({ length: 21 }, (_, index) => ({
      input: `docs/f${index}.pdf`,
      error: 'bad',
    }));
    const health = libraryHealth(input({
      syncReport: { ok: false, failed: 21, errors },
    }));
    const files = health.items.filter((item) => item.kind === 'failedFile');
    expect(files).toHaveLength(20);
    expect(files[0]?.path).toBe('C:\\library\\docs\\f0.pdf');
    expect(files[0]?.text).toBe('f0.pdf');
    expect(files[0]?.actions).toEqual(['retry', 'convertWithOptions', 'showInFolder']);
    expect(health.items.find((item) => item.kind === 'moreFailures')?.text).toBe('and 1 more');
    expect(health.label).toBe('Needs attention (21)');

    const posix = libraryHealth(input({
      libraryPath: '/library',
      syncReport: { failed: 1, errors: [{ input: '/tmp/other.pdf', error: 'bad' }] },
    }));
    expect(posix.items.find((item) => item.kind === 'failedFile')?.path).toBe('/tmp/other.pdf');
  });

  it('offers try again when the index refresh itself fails', () => {
    const health = libraryHealth(input({
      syncReport: { ok: false, failed: 1, errors: [{ input: '.vera/index', error: 'locked' }] },
    }));
    const problem = health.items.find((item) => item.kind === 'syncError');
    expect(problem?.text).toBe('Library index could not be updated');
    expect(problem?.path).toBe('C:\\library\\.vera\\index');
    expect(problem?.actions).toEqual(['tryAgain', 'openConvertLog']);
  });

  it('uses the running task phrase and hides the index section while indexing', () => {
    const health = libraryHealth(input({
      converting: true,
      workMessage: 'Converting 2 of 3',
      indexReport: { skipped: 2 },
    }));
    expect(health.state).toBe('working');
    expect(health.label).toBe('Converting 2 of 3');
    expect(health.items.some((item) => item.kind === 'skippedIndex')).toBe(true);

    const indexing = libraryHealth(input({ indexing: 'update' }));
    expect(indexing.state).toBe('working');
    expect(indexing.label).toBe('Updating index…');
    expect(indexing.items.some((item) => item.kind === 'index')).toBe(false);
  });

  it('checks until the first index status arrives', () => {
    expect(libraryHealth(input({ index: null, indexChecking: true })).state).toBe('checking');
    expect(libraryHealth(input({ index: null, indexChecking: false })).state).toBe('setup');
  });

  it('ignores a busy snapshot when deciding attention', () => {
    const health = libraryHealth(input({
      syncReport: { busy: true, ok: false, error: 'still running' },
    }));
    expect(health.state).toBe('ready');
  });
});

describe('nextSyncReport', () => {
  it('keeps the stored result when the next report is busy, cancelled, or missing', () => {
    const previous: LibrarySyncReport = {
      managed: true,
      failed: 1,
      errors: [{ input: 'a.pdf', error: 'bad' }],
    };
    expect(nextSyncReport(previous, { managed: true, busy: true })).toBe(previous);
    expect(nextSyncReport(previous, { managed: true, cancelled: true })).toBe(previous);
    expect(nextSyncReport(previous, null)).toBe(previous);
    expect(nextSyncReport(undefined, { busy: true })).toBeNull();
    const finished: LibrarySyncReport = { managed: true, converted: 1, failed: 0 };
    expect(nextSyncReport(previous, finished)).toBe(finished);
  });
});

describe('libraryActivityLabel', () => {
  it('shortens index progress and keeps sync phrases', () => {
    expect(libraryActivityLabel({
      kind: 'index',
      label: 'Updating index',
      operation: 'update',
      phase: 'indexing',
      completed: 2,
      total: 4,
    })).toBe('Updating index 2 of 4');
    expect(libraryActivityLabel({
      kind: 'index',
      label: 'Building index',
      operation: 'build',
      phase: 'finalizing',
      completed: 4,
      total: 4,
    })).toBe('Updating library index…');
    expect(libraryActivityLabel({
      kind: 'librarySync',
      label: 'Syncing library',
      message: 'Converting 2 of 3',
    })).toBe('Converting 2 of 3');
  });
});
