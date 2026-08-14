import type { LibraryIndexStatus, WorkspaceFolderResult } from '../types';

export const FOLDERS_STORAGE_KEY = 'vera.folders';
export const INDEX_STATUSES_STORAGE_KEY = 'vera.indexStatuses';
export const ACTIVE_LIBRARY_STORAGE_KEY = 'vera.activeLibraryPath';

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

export function readSavedActiveLibraryPath(storage: StorageReader = localStorage): string {
  try {
    return storage.getItem(ACTIVE_LIBRARY_STORAGE_KEY) || '';
  } catch {
    return '';
  }
}

/**
 * Restore the last active library immediately. Other folders can refresh
 * their index badges in parallel instead of blocking Explorer collapse.
 */
export function workspaceRestorePlan(
  availablePaths: string[],
  savedActive: string,
): { restoreActive: string | null; refreshPaths: string[] } {
  const restoreActive = savedActive && availablePaths.includes(savedActive)
    ? savedActive
    : null;
  return {
    restoreActive,
    refreshPaths: availablePaths.filter((folderPath) => folderPath !== restoreActive),
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
