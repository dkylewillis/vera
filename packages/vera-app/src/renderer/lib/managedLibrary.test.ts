import { describe, expect, it } from 'vitest';

import {
  convertedArchivePath,
  librarySyncProblem,
  librarySyncSummary,
  librarySyncTaskUpdate,
  prepareManagedLibrary,
} from './managedLibrary';

describe('convertedArchivePath', () => {
  it('matches the file that was just converted', () => {
    const report = {
      actions: [{
        action: 'convert',
        source: 'new/zones.docx',
        output: 'C:\\library\\.vera\\archives\\new\\zones.docx.vera',
        notes: ["Headers and footers aren't included in search. VERA searches the main body text."],
      }],
    };
    expect(convertedArchivePath('C:\\library\\new\\zones.docx', report))
      .toBe('C:\\library\\.vera\\archives\\new\\zones.docx.vera');
    expect(convertedArchivePath('C:\\library\\new\\other.docx', report)).toBe('');
    expect(convertedArchivePath('C:\\library\\new\\zones.docx', { actions: [{ action: 'unchanged', source: 'new/zones.docx' }] })).toBe('');
  });
});

describe('librarySyncTaskUpdate', () => {
  it('describes sync steps and the index refresh that follows', () => {
    expect(librarySyncTaskUpdate({ phase: 'convert', completed: 1, total: 3, input: 'b.docx' }))
      .toMatchObject({ message: 'Converting 2 of 3', currentItem: 'b.docx', completed: 1, total: 3 });
    expect(librarySyncTaskUpdate({ phase: 'move', completed: 0, total: 1 }).message).toBe('Moving archives 1 of 1');
    expect(librarySyncTaskUpdate({ phase: 'indexing', completed: 4, total: 9, input: '' }))
      .toMatchObject({ message: 'Updating library index…', total: 0 });
  });
});

describe('librarySyncProblem', () => {
  it('reports busy libraries and per-file errors', () => {
    expect(librarySyncProblem({ managed: true, ok: true, converted: 1 })).toBeNull();
    expect(librarySyncProblem({ managed: true, busy: true })).toContain('Another VERA process is updating');
    expect(librarySyncProblem(null)).toContain('Library sync failed');
    const errors = Array.from({ length: 4 }, (_, i) => ({ input: `f${i}.pdf`, error: 'bad' }));
    expect(librarySyncProblem({ managed: true, ok: false, errors })).toBe(
      'Some files did not convert:\nf0.pdf: bad\nf1.pdf: bad\nf2.pdf: bad\n…and 1 more',
    );
  });
});
import type { VeraResponse } from '../types';

describe('librarySyncSummary', () => {
  it('describes confirmation and completed syncs, and stays quiet while another process syncs', () => {
    expect(librarySyncSummary({ managed: false })).toBe('');
    expect(librarySyncSummary({ managed: true, needs_confirmation: true })).toBe('Confirm before removing archives');
    expect(librarySyncSummary({ managed: true, busy: true })).toBe('');
    expect(librarySyncSummary({ managed: true, converted: 2, moved: 1 })).toBe('2 converted, 1 moved');
  });
});

describe('prepareManagedLibrary', () => {
  it('asks before adopting sibling archives and skips folders already in a library', async () => {
    const calls: string[] = [];
    const request = async <T>(payload: Record<string, unknown>): Promise<VeraResponse<T>> => {
      calls.push(String(payload.action));
      if (payload.action === 'library_status') {
        return { ok: true, result: { managed: false, adoptable: ['notes.md'] } as T };
      }
      expect(payload.adopt).toBe(true);
      return { ok: true, result: { library_id: 'abc' } as T };
    };
    await prepareManagedLibrary('C:\\docs', request, { askAdopt: async () => true, model: 'hashing' });
    expect(calls).toEqual(['library_status', 'library_init']);

    const skipped = await prepareManagedLibrary('C:\\docs\\Plans', async <T>() => ({
      ok: true,
      result: { managed: false, inside_library: true } as T,
    }));
    expect(skipped?.inside_library).toBe(true);
  });
});
