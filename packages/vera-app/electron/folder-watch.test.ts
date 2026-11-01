import { describe, expect, it } from 'vitest';

import { isManagedLibraryEvent, librarySyncDecision } from './folder-watch.js';

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
