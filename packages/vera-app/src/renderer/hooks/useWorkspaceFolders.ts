import { useEffect, useRef, useState } from 'react';
import {
  dropFolder,
  persistFolderPaths,
  readCachedIndexStatuses,
  readSavedActiveLibraryPath,
  readSavedFolderPaths,
  replaceListedFolder,
  upsertFolder,
  workspaceRestorePlan,
} from '../lib/workspaceFolders';
import type { LibraryIndexStatus, WorkspaceFolderResult } from '../types';

export type UseWorkspaceFoldersOptions = {
  onOpenLibrary: (folderPath: string) => Promise<void> | void;
  onFolderRemoved: (folderPath: string) => void;
  refreshIndexStatus: (folderPath: string, verifyHashes?: boolean) => Promise<LibraryIndexStatus | null>;
  onIndexStatusesHydrated: (statuses: Record<string, LibraryIndexStatus>) => void;
  onWatchedFolderChanged?: (folderPath: string) => void;
  onFolderWillRefresh?: (folderPath: string) => void;
  onFolderRefreshed?: (folderPath: string) => void;
};

export function useWorkspaceFolders(options: UseWorkspaceFoldersOptions): {
  folders: WorkspaceFolderResult[];
  busyFolderPath: string;
  addFolderFromPath: (dir: string) => Promise<void>;
  addFolder: () => Promise<void>;
  removeFolder: (folderPath: string) => void;
  refreshFolder: (folderPath: string, refreshOptions?: { showBusy?: boolean }) => Promise<void>;
  loadFolders: (isCanceled?: () => boolean) => Promise<void>;
} {
  const [folders, setFolders] = useState<WorkspaceFolderResult[]>([]);
  const [busyFolderPath, setBusyFolderPath] = useState('');
  const optionsRef = useRef(options);
  optionsRef.current = options;

  async function addFolderFromPath(dir: string) {
    const folder = await window.vera.listFolder(dir);
    if (!folder) return;
    setFolders((prev) => {
      const next = upsertFolder(prev, folder);
      persistFolderPaths(next.map((entry) => entry.path));
      return next;
    });
    await optionsRef.current.onOpenLibrary(folder.path);
  }

  async function addFolder() {
    const dir = await window.vera.pickFolder();
    if (!dir) return;
    await addFolderFromPath(dir);
  }

  function removeFolder(folderPath: string) {
    setFolders((prev) => {
      const next = dropFolder(prev, folderPath);
      persistFolderPaths(next.map((entry) => entry.path));
      return next;
    });
    optionsRef.current.onFolderRemoved(folderPath);
  }

  async function refreshFolder(folderPath: string, refreshOptions: { showBusy?: boolean } = {}) {
    const showBusy = refreshOptions.showBusy ?? true;
    optionsRef.current.onFolderWillRefresh?.(folderPath);
    if (showBusy) setBusyFolderPath(folderPath);
    try {
      const folder = await window.vera.listFolder(folderPath);
      if (folder) setFolders((prev) => replaceListedFolder(prev, folder));
      await optionsRef.current.refreshIndexStatus(folderPath);
      optionsRef.current.onFolderRefreshed?.(folderPath);
    } finally {
      if (showBusy) {
        setBusyFolderPath((current) => (current === folderPath ? '' : current));
      }
    }
  }

  async function loadFolders(isCanceled: () => boolean = () => false) {
    const saved = readSavedFolderPaths();
    if (saved.length === 0) return;
    const loaded = await Promise.all(saved.map((dir) => window.vera.listFolder(dir)));
    if (isCanceled()) return;
    const available = loaded.filter((entry): entry is WorkspaceFolderResult => entry !== null);
    optionsRef.current.onIndexStatusesHydrated(
      readCachedIndexStatuses(new Set(available.map((entry) => entry.path))),
    );
    setFolders(available);
    if (isCanceled()) return;
    const { restoreActive, refreshPaths } = workspaceRestorePlan(
      available.map((entry) => entry.path),
      readSavedActiveLibraryPath(),
    );
    const restore = restoreActive
      ? Promise.resolve(optionsRef.current.onOpenLibrary(restoreActive))
      : Promise.resolve();
    const refresh = Promise.all(
      refreshPaths.map((folderPath) => optionsRef.current.refreshIndexStatus(folderPath)),
    );
    await Promise.all([restore, refresh]);
  }

  const folderPathsKey = folders.map((folder) => folder.path).join('\n');

  useEffect(() => {
    const folderPaths = folderPathsKey ? folderPathsKey.split('\n') : [];
    void window.vera.setWatchedFolders(folderPaths);
  }, [folderPathsKey]);

  useEffect(() => window.vera.onFolderChanged((folderPath) => {
    optionsRef.current.onWatchedFolderChanged?.(folderPath);
    void window.vera.listFolder(folderPath).then((folder) => {
      if (!folder) return;
      setFolders((prev) => replaceListedFolder(prev, folder));
    });
    void optionsRef.current.refreshIndexStatus(folderPath);
  }), []);

  return {
    folders,
    busyFolderPath,
    addFolderFromPath,
    addFolder,
    removeFolder,
    refreshFolder,
    loadFolders,
  };
}
