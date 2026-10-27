import type { LibraryIndexStatus, WorkspaceFolderResult } from '../types';
import { isPathInsideFolder, sameFsPath } from './formatting';

export const FOLDERS_STORAGE_KEY = 'vera.folders';
export const INDEX_STATUSES_STORAGE_KEY = 'vera.indexStatuses';
export const ACTIVE_LIBRARY_STORAGE_KEY = 'vera.activeLibraryPath';
export const LIBRARY_PATHS_STORAGE_KEY = 'vera.libraryPaths';

type StorageReader = { getItem(key: string): string | null };
type StorageWriter = { setItem(key: string, value: string): void };

export function readSavedFolderPaths(storage: StorageReader = localStorage): string[] {
  try {
    const saved = JSON.parse(storage.getItem(FOLDERS_STORAGE_KEY) || '[]') as unknown;
    return Array.isArray(saved) ? saved as string[] : [];
  } catch {
    return [];
  }
}

export function persistFolderPaths(paths: string[], storage: StorageWriter = localStorage): void {
  storage.setItem(FOLDERS_STORAGE_KEY, JSON.stringify(paths));
}

/**
 * Open folders that are libraries. Workspaces saved before libraries and
 * plain folders were distinguished have no key yet; every folder they opened
 * was a library.
 */
export function readSavedLibraryPaths(storage: StorageReader = localStorage): string[] {
  try {
    const raw = storage.getItem(LIBRARY_PATHS_STORAGE_KEY);
    if (raw === null) return readSavedFolderPaths(storage);
    const saved = JSON.parse(raw) as unknown;
    return Array.isArray(saved) ? saved.filter((item): item is string => typeof item === 'string') : [];
  } catch {
    return [];
  }
}

export function persistLibraryPaths(paths: string[], storage: StorageWriter = localStorage): void {
  try {
    storage.setItem(LIBRARY_PATHS_STORAGE_KEY, JSON.stringify(paths));
  } catch {
    // The folder list still restores; plain folders would reopen as libraries.
  }
}

export function readSavedActiveLibraryPath(storage: StorageReader = localStorage): string {
  try {
    return storage.getItem(ACTIVE_LIBRARY_STORAGE_KEY) || '';
  } catch {
    return '';
  }
}

/**
 * Restore the last active library immediately. Other libraries can refresh
 * their index badges in parallel instead of blocking Explorer collapse.
 * Plain folders have no index badge and are never restored as active.
 */
export function workspaceRestorePlan(
  availablePaths: string[],
  savedActive: string,
  libraryPaths: string[] = availablePaths,
): { restoreActive: string | null; refreshPaths: string[] } {
  const libraries = availablePaths.filter((folderPath) => libraryPaths.includes(folderPath));
  const restoreActive = savedActive && libraries.includes(savedActive)
    ? savedActive
    : null;
  return {
    restoreActive,
    refreshPaths: libraries.filter((folderPath) => folderPath !== restoreActive),
  };
}

export function upsertFolder(
  folders: WorkspaceFolderResult[],
  folder: WorkspaceFolderResult,
): WorkspaceFolderResult[] {
  return [...folders.filter((entry) => entry.path !== folder.path), folder];
}

export function replaceListedFolder(
  folders: WorkspaceFolderResult[],
  folder: WorkspaceFolderResult,
): WorkspaceFolderResult[] {
  return folders.map((entry) => (entry.path === folder.path ? folder : entry));
}

export function dropFolder(
  folders: WorkspaceFolderResult[],
  folderPath: string,
): WorkspaceFolderResult[] {
  return folders.filter((entry) => entry.path !== folderPath);
}

export type NestedLibraryConflict =
  | { kind: 'inside'; path: string; library: string }
  | { kind: 'contains'; path: string; libraries: string[] };

/**
 * Report when a folder about to become a library sits inside an existing
 * library (closest one wins) or contains existing libraries.
 */
export function nestedLibraryConflict(
  folderPath: string,
  libraryPaths: string[],
): NestedLibraryConflict | null {
  const others = libraryPaths.filter((entry) => !sameFsPath(entry, folderPath));
  const parents = others
    .filter((library) => isPathInsideFolder(folderPath, library))
    .sort((left, right) => right.length - left.length);
  if (parents.length) return { kind: 'inside', path: folderPath, library: parents[0] };
  const children = others.filter((library) => isPathInsideFolder(library, folderPath));
  return children.length ? { kind: 'contains', path: folderPath, libraries: children } : null;
}

export function isValidCachedIndexStatus(status: unknown): status is LibraryIndexStatus {
  return Boolean(
    status
    && typeof status === 'object'
    && typeof (status as LibraryIndexStatus).exists === 'boolean'
    && typeof (status as LibraryIndexStatus).fresh === 'boolean'
    && Array.isArray((status as LibraryIndexStatus).reasons),
  );
}

export function readCachedIndexStatuses(
  availablePaths: Set<string>,
  storage: StorageReader = localStorage,
): Record<string, LibraryIndexStatus> {
  try {
    const cached = JSON.parse(storage.getItem(INDEX_STATUSES_STORAGE_KEY) || '{}') as unknown;
    if (!cached || typeof cached !== 'object') return {};
    return Object.fromEntries(
      Object.entries(cached as Record<string, unknown>).flatMap(([folderPath, status]) => (
        availablePaths.has(folderPath) && isValidCachedIndexStatus(status)
          ? [[folderPath, status] as const]
          : []
      )),
    );
  } catch {
    return {};
  }
}
