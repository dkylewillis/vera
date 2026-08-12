import { describe, expect, it } from 'vitest';
import { syncCollapsedFolders } from './explorer';

describe('syncCollapsedFolders', () => {
  it('preserves expand/collapse state when no library is active', () => {
    expect(syncCollapsedFolders(['/a', '/b'], '', ['/b'])).toEqual(['/b']);
  });

  it('drops collapsed paths for folders that were closed', () => {
    expect(syncCollapsedFolders(['/a'], '', ['/a', '/gone'])).toEqual(['/a']);
  });

  it('keeps the active library expanded and collapses the rest', () => {
    expect(syncCollapsedFolders(['/a', '/b', '/c'], '/b', ['/a'])).toEqual(['/a', '/c']);
  });

  it('expands a lone active library', () => {
    expect(syncCollapsedFolders(['/only'], '/only', ['/only'])).toEqual([]);
  });
});
