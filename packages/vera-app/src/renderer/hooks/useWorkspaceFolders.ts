import { useEffect, useRef, useState } from 'react';
import {
  dropFolder,
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
  type NestedLibraryConflict,
} from '../lib/workspaceFolders';
import type { LibraryIndexStatus, WorkspaceFolderResult } from '../types';

export type WorkspaceFolderKind = 'library' | 'folder';

export type UseWorkspaceFoldersOptions = {
  onOpenLibrary: (folderPath: string) => Promise<void> | void;
  onFolderRemoved: (folderPath: string) => void;
  refreshIndexStatus: (folderPath: string, verifyHashes?: boolean) => Promise<LibraryIndexStatus | null>;
  onIndexStatusesHydrated: (statuses: Record<string, LibraryIndexStatus>) => void;
  onWatchedFolderChanged?: (folderPath: string) => void;
  onFolderWillRefresh?: (folderPath: string) => void;
  onFolderRefreshed?: (folderPath: string) => void;
  /** Called instead of adding a library that overlaps an existing one. */
  onNestedLibrary?: (conflict: NestedLibraryConflict) => void;
};

export type AddFolderOptions = { allowNested?: boolean };

export function useWorkspaceFolders(options: UseWorkspaceFoldersOptions): {
  folders: WorkspaceFolderResult[];
  libraryPaths: string[];
  busyFolderPath: string;
  addFolderFromPath: (dir: string, kind?: WorkspaceFolderKind, addOptions?: AddFolderOptions) => Promise<void>;
  addFolder: (kind?: WorkspaceFolderKind) => Promise<void>;
  removeFolder: (folderPath: string) => void;
  setFolderKind: (folderPath: string, kind: WorkspaceFolderKind) => void;
  refreshFolder: (folderPath: string, refreshOptions?: { showBusy?: boolean }) => Promise<void>;
  loadFolders: (isCanceled?: () => boolean) => Promise<void>;
} {
  const [folders, setFolders] = useState<WorkspaceFolderResult[]>([]);
  const [libraryPaths, setLibraryPaths] = useState<string[]>(() => readSavedLibraryPaths());
  const [busyFolderPath, setBusyFolderPath] = useState('');
  const optionsRef = useRef(options);
  optionsRef.current = options;
  const libraryPathsRef = useRef(libraryPaths);
  libraryPathsRef.current = libraryPaths;

  function updateLibraryPaths(update: (prev: string[]) => string[]) {
    const next = update(libraryPathsRef.current);
    libraryPathsRef.current = next;
    persistLibraryPaths(next);
    setLibraryPaths(next);
  }

  async function addFolderFromPath(
    dir: string,
    kind: WorkspaceFolderKind = 'library',
    addOptions: AddFolderOptions = {},
  ) {
    const folder = await window.vera.listFolder(dir);
    if (!folder) return;
    const onNestedLibrary = optionsRef.current.onNestedLibrary;
    const alreadyLibrary = libraryPathsRef.current.includes(folder.path);
    if (kind === 'library' && !alreadyLibrary && !addOptions.allowNested && onNestedLibrary) {
      const conflict = nestedLibraryConflict(folder.path, libraryPathsRef.current);
      if (conflict) {
        onNestedLibrary(conflict);
        return;
      }
    }
    setFolders((prev) => {
      const next = upsertFolder(prev, folder);
      persistFolderPaths(next.map((entry) => entry.path));
      return next;
    });
    // Opening an existing library as a folder leaves it a library.
    updateLibraryPaths((prev) => (
      kind === 'library' && !prev.includes(folder.path) ? [...prev, folder.path] : prev
    ));
    if (libraryPathsRef.current.includes(folder.path)) {
      await optionsRef.current.onOpenLibrary(folder.path);
    }
  }

  async function addFolder(kind: WorkspaceFolderKind = 'library') {
    const dir = await window.vera.pickFolder();
    if (!dir) return;
    await addFolderFromPath(dir, kind);
  }

  function removeFolder(folderPath: string) {
    setFolders((prev) => {
      const next = dropFolder(prev, folderPath);
      persistFolderPaths(next.map((entry) => entry.path));
      return next;
    });
    updateLibraryPaths((prev) => prev.filter((entry) => entry !== folderPath));
    optionsRef.current.onFolderRemoved(folderPath);
  }

  function setFolderKind(folderPath: string, kind: WorkspaceFolderKind) {
    updateLibraryPaths((prev) => {
      const without = prev.filter((entry) => entry !== folderPath);
      return kind === 'library' ? [...without, folderPath] : without;
    });
  }

  async function refreshFolder(folderPath: string, refreshOptions: { showBusy?: boolean } = {}) {
    const showBusy = refreshOptions.showBusy ?? true;
    optionsRef.current.onFolderWillRefresh?.(folderPath);
    if (showBusy) setBusyFolderPath(folderPath);
    try {
      const folder = await window.vera.listFolder(folderPath);
      if (folder) setFolders((prev) => replaceListedFolder(prev, folder));
      if (libraryPathsRef.current.includes(folderPath)) {
        await optionsRef.current.refreshIndexStatus(folderPath);
      }
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
    // Pin the migrated library list so folders opened later stay plain folders.
    updateLibraryPaths((prev) => prev);
    if (isCanceled()) return;
    const { restoreActive, refreshPaths } = workspaceRestorePlan(
      available.map((entry) => entry.path),
      readSavedActiveLibraryPath(),
      libraryPathsRef.current,
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
    if (libraryPathsRef.current.includes(folderPath)) {
      void optionsRef.current.refreshIndexStatus(folderPath);
    }
  }), []);

  return {
    folders,
    libraryPaths,
    busyFolderPath,
    addFolderFromPath,
    addFolder,
    removeFolder,
    setFolderKind,
    refreshFolder,
    loadFolders,
  };
}
