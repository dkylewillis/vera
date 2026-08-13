import { describe, expect, it } from 'vitest';
import type { LibraryIndexStatus, WorkspaceFolderResult } from '../types';
import {
  dropFolder,
  FOLDERS_STORAGE_KEY,
  persistFolderPaths,
  readCachedIndexStatuses,
  readSavedFolderPaths,
  replaceListedFolder,
  upsertFolder,
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
