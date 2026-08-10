import { describe, expect, it } from 'vitest';
import { collapsedFoldersForActiveLibrary } from './explorer';

describe('collapsedFoldersForActiveLibrary', () => {
  it('collapses every folder when none is active', () => {
    expect(collapsedFoldersForActiveLibrary(['/a', '/b'], '')).toEqual(['/a', '/b']);
  });

  it('keeps the active library expanded and collapses the rest', () => {
    expect(collapsedFoldersForActiveLibrary(['/a', '/b', '/c'], '/b')).toEqual(['/a', '/c']);
  });

  it('expands a lone active library', () => {
    expect(collapsedFoldersForActiveLibrary(['/only'], '/only')).toEqual([]);
  });
});
