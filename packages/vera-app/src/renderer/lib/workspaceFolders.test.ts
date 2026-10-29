import { describe, expect, it } from 'vitest';
import type { LibraryIndexStatus, WorkspaceFolderResult } from '../types';
import {
  ACTIVE_LIBRARY_STORAGE_KEY,
  dropFolder,
  FOLDERS_STORAGE_KEY,
  LIBRARY_PATHS_STORAGE_KEY,
  nestedLibraryConflict,
  persistFolderPaths,
  persistLibraryPaths,
  readCachedIndexStatuses,
  readSavedActiveLibraryPath,
  readSavedFolderPaths,
  readSavedLibraryPaths,
  replaceListedFolder,
  upsertFolder,
  workspaceRestorePlan,
} from './workspaceFolders';

function memoryStorage(initial: Record<string, string> = {}) {
  const data = { ...initial };
  return {
    getItem(key: string) {
      return Object.prototype.hasOwnProperty.call(data, key) ? data[key] : null;
    },
    setItem(key: string, value: string) {
      data[key] = value;
    },
  };
}

const folder = (path: string): WorkspaceFolderResult => ({ path, name: path, entries: [] });

describe('readSavedFolderPaths', () => {
  it('returns persisted folder paths', () => {
    const storage = memoryStorage({
      [FOLDERS_STORAGE_KEY]: JSON.stringify(['C:\\docs', 'C:\\library']),
    });
    expect(readSavedFolderPaths(storage)).toEqual(['C:\\docs', 'C:\\library']);
  });

  it('returns an empty list for missing or invalid JSON', () => {
    expect(readSavedFolderPaths(memoryStorage())).toEqual([]);
    expect(readSavedFolderPaths(memoryStorage({ [FOLDERS_STORAGE_KEY]: '{' }))).toEqual([]);
    expect(readSavedFolderPaths(memoryStorage({ [FOLDERS_STORAGE_KEY]: '{}' }))).toEqual([]);
  });
});

describe('persistFolderPaths', () => {
  it('writes folder paths as JSON', () => {
    const storage = memoryStorage();
    persistFolderPaths(['C:\\docs'], storage);
    expect(storage.getItem(FOLDERS_STORAGE_KEY)).toBe(JSON.stringify(['C:\\docs']));
  });
});

describe('readSavedActiveLibraryPath', () => {
  it('returns the persisted active library', () => {
    const storage = memoryStorage({
      [ACTIVE_LIBRARY_STORAGE_KEY]: 'C:\\library',
    });
    expect(readSavedActiveLibraryPath(storage)).toBe('C:\\library');
  });

  it('returns empty when unset', () => {
    expect(readSavedActiveLibraryPath(memoryStorage())).toBe('');
  });
});

describe('workspaceRestorePlan', () => {
  it('restores the saved library immediately and refreshes the rest', () => {
    expect(workspaceRestorePlan(['C:\\a', 'C:\\b', 'C:\\c'], 'C:\\b')).toEqual({
      restoreActive: 'C:\\b',
      refreshPaths: ['C:\\a', 'C:\\c'],
    });
  });

  it('refreshes every listed folder when none is still saved as active', () => {
    expect(workspaceRestorePlan(['C:\\a', 'C:\\b'], 'C:\\gone')).toEqual({
      restoreActive: null,
      refreshPaths: ['C:\\a', 'C:\\b'],
    });
    expect(workspaceRestorePlan(['C:\\a'], '')).toEqual({
      restoreActive: null,
      refreshPaths: ['C:\\a'],
    });
  });

  it('never restores or index-checks a plain folder', () => {
    expect(workspaceRestorePlan(['C:\\lib', 'C:\\plain'], 'C:\\plain', ['C:\\lib'])).toEqual({
      restoreActive: null,
      refreshPaths: ['C:\\lib'],
    });
  });
});

describe('readSavedLibraryPaths', () => {
  it('treats every saved folder as a library before the key exists', () => {
    const storage = memoryStorage({
      [FOLDERS_STORAGE_KEY]: JSON.stringify(['C:\\docs', 'C:\\library']),
    });
    expect(readSavedLibraryPaths(storage)).toEqual(['C:\\docs', 'C:\\library']);
  });

  it('round-trips the persisted library list', () => {
    const storage = memoryStorage({
      [FOLDERS_STORAGE_KEY]: JSON.stringify(['C:\\docs', 'C:\\library']),
    });
    persistLibraryPaths(['C:\\library'], storage);
    expect(storage.getItem(LIBRARY_PATHS_STORAGE_KEY)).toBe(JSON.stringify(['C:\\library']));
    expect(readSavedLibraryPaths(storage)).toEqual(['C:\\library']);
    persistLibraryPaths([], storage);
    expect(readSavedLibraryPaths(storage)).toEqual([]);
  });
});

describe('folder list updates', () => {
  it('upserts by path and keeps the new entry last', () => {
    const updated = folder('C:\\docs');
    updated.name = 'docs';
    expect(upsertFolder([folder('C:\\docs'), folder('C:\\other')], updated)).toEqual([
      folder('C:\\other'),
      updated,
    ]);
  });

  it('replaces a listed folder in place', () => {
    const updated = folder('C:\\docs');
    updated.entries = [{ path: 'C:\\docs\\a.vera', name: 'a.vera', relativePath: 'a.vera', type: 'vera' }];
    expect(replaceListedFolder([folder('C:\\docs'), folder('C:\\other')], updated)).toEqual([
      updated,
      folder('C:\\other'),
    ]);
  });

  it('drops a folder by path', () => {
    expect(dropFolder([folder('C:\\docs'), folder('C:\\other')], 'C:\\docs')).toEqual([
      folder('C:\\other'),
    ]);
  });
});

describe('readCachedIndexStatuses', () => {
  const fresh: LibraryIndexStatus = {
    directory: 'C:\\docs',
    index: 'C:\\docs\\.vera-index',
    exists: true,
    fresh: true,
    reasons: [],
  };

  it('keeps valid statuses for folders that are still open', () => {
    const storage = memoryStorage({
      'vera.indexStatuses': JSON.stringify({
        'C:\\docs': fresh,
        'C:\\gone': fresh,
        'C:\\bad': { exists: true },
      }),
    });
    expect(readCachedIndexStatuses(new Set(['C:\\docs', 'C:\\bad']), storage)).toEqual({
      'C:\\docs': fresh,
    });
  });

  it('ignores missing or invalid cache JSON', () => {
    expect(readCachedIndexStatuses(new Set(['C:\\docs']), memoryStorage())).toEqual({});
    expect(readCachedIndexStatuses(new Set(['C:\\docs']), memoryStorage({ 'vera.indexStatuses': '[' }))).toEqual({});
  });
});

describe('nestedLibraryConflict', () => {
  const libraries = ['C:\\work', 'C:\\work\\projects', 'D:\\codes'];

  it('reports the closest library that already contains the folder', () => {
    expect(nestedLibraryConflict('C:\\work\\projects\\smith', libraries)).toEqual({
      kind: 'inside',
      path: 'C:\\work\\projects\\smith',
      library: 'C:\\work\\projects',
    });
  });

  it('reports libraries inside a folder being added around them', () => {
    expect(nestedLibraryConflict('D:\\', ['D:\\codes', 'D:\\specs\\2024'])).toEqual({
      kind: 'contains',
      path: 'D:\\',
      libraries: ['D:\\codes', 'D:\\specs\\2024'],
    });
  });

  it('ignores the folder itself, siblings, and look-alike prefixes', () => {
    expect(nestedLibraryConflict('C:\\work', ['C:\\work'])).toBeNull();
    expect(nestedLibraryConflict('c:\\WORK\\', ['C:\\work'])).toBeNull();
    expect(nestedLibraryConflict('C:\\workshop', ['C:\\work'])).toBeNull();
    expect(nestedLibraryConflict('E:\\other', libraries)).toBeNull();
  });
});
