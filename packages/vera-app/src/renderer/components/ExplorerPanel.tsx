import { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Database,
  FileText,
  Folder,
  FolderOpen,
  RefreshCw,
} from 'lucide-react';
import { VeraIcon } from './VeraIcon';
import {
  applyFileListCheckbox,
  applyFileListSelection,
  explorerFileMatchesFilter,
  explorerRowTone,
  explorerSelectionAfterFileList,
  partitionExplorerSelection,
  convertibleSelection,
  pruneExplorerSelectionForFilter,
  visibleExplorerEntries,
  type ExplorerFileFilter,
} from '../lib/explorer';
import { fileName, showInFolderLabel, type ExplorerSelection } from '../lib/formatting';
import type {
  FolderEntry,
  LibraryIndexBuildReport,
  LibraryIndexStatus,
  WorkspaceFolderResult,
} from '../types';

type FolderContextMenu = { path: string; x: number; y: number };
type EntryContextMenu = { entry: FolderEntry; folderPath: string; x: number; y: number };

export type ExplorerFileSelection = {
  selectedFiles: string[];
  selectedPdfs: string[];
  selectionAnchorPath: string | null;
  explorerSelection: ExplorerSelection | null;
};

export function ExplorerPanel({
  folders,
  activeLibraryPath,
  path,
  selectedFiles,
  selectedPdfs,
  selectionAnchorPath,
  explorerSelection,
  explorerFileFilter,
  collapsedFolders,
  pendingSourcePath,
  sourceDocumentPath,
  sourceLoading,
  indexStatuses,
  indexStatusChecking,
  indexReports,
  indexingFolders,
  busyFolderPath,
  busyAction,
  convertLocked,
  escapeBlocked,
  onClearFileSelection,
  onAddFolder,
  onFileFilterChange,
  onCollapsedFoldersChange,
  onFileSelectionChange,
  onSelectFolder,
  onOpenLibraryInfo,
  onUpdateTargetPath,
  onPreview,
  onShowIndexReport,
  onConvertFolder,
  onConvertSelected,
  onReconvert,
  onManageIndex,
  onRefreshFolder,
  onRevealInFolder,
  onRemoveFolder,
  onTrashEntry,
}: {
  folders: WorkspaceFolderResult[];
  activeLibraryPath: string;
  path: string;
  selectedFiles: string[];
  selectedPdfs: string[];
  selectionAnchorPath: string | null;
  explorerSelection: ExplorerSelection | null;
  explorerFileFilter: ExplorerFileFilter;
  collapsedFolders: string[];
  pendingSourcePath: string;
  sourceDocumentPath: string;
  sourceLoading: boolean;
  indexStatuses: Record<string, LibraryIndexStatus>;
  indexStatusChecking: Record<string, boolean>;
  indexReports: Record<string, LibraryIndexBuildReport>;
  indexingFolders: Record<string, 'build' | 'update'>;
  busyFolderPath: string;
  busyAction: string | null;
  convertLocked: boolean;
  escapeBlocked: boolean;
  onClearFileSelection: () => boolean;
  onAddFolder: () => void;
  onFileFilterChange: (filter: ExplorerFileFilter) => void;
  onCollapsedFoldersChange: (update: (prev: string[]) => string[]) => void;
  onFileSelectionChange: (next: ExplorerFileSelection) => void;
  onSelectFolder: (folderPath: string) => void;
  onOpenLibraryInfo: (folderPath: string) => void;
  onUpdateTargetPath: (value: string) => void;
  onPreview: (entry: FolderEntry) => void;
  onShowIndexReport: (report: LibraryIndexBuildReport) => void;
  onConvertFolder: (folderPath: string) => void;
  onConvertSelected: (paths: string[]) => void;
  onReconvert: (entry: FolderEntry, folderPath: string) => void;
  onManageIndex: (folderPath: string) => void;
  onRefreshFolder: (folderPath: string) => void;
  onRevealInFolder: (targetPath: string) => void;
  onRemoveFolder: (folderPath: string) => void;
  onTrashEntry: (entry: FolderEntry, folderPath: string) => void;
}) {
  const [folderContextMenu, setFolderContextMenu] = useState<FolderContextMenu | null>(null);
  const folderContextMenuFirstActionRef = useRef<HTMLButtonElement | null>(null);
  const folderContextMenuTriggerRef = useRef<HTMLElement | null>(null);
  const [entryContextMenu, setEntryContextMenu] = useState<EntryContextMenu | null>(null);
  const entryContextMenuActionRef = useRef<HTMLButtonElement | null>(null);
  const entryContextMenuTriggerRef = useRef<HTMLElement | null>(null);

  const visibleExplorerFiles = useMemo(
    () => visibleExplorerEntries(folders, collapsedFolders, explorerFileFilter),
    [folders, collapsedFolders, explorerFileFilter],
  );
  const fileSelectionRef = useRef({ selectedFiles, selectedPdfs, selectionAnchorPath });
  fileSelectionRef.current = { selectedFiles, selectedPdfs, selectionAnchorPath };

  function commitFileSelection(next: ExplorerFileSelection) {
    fileSelectionRef.current = {
      selectedFiles: next.selectedFiles,
      selectedPdfs: next.selectedPdfs,
      selectionAnchorPath: next.selectionAnchorPath,
    };
    onFileSelectionChange(next);
  }
  const folderMenuSourceCount = folderContextMenu
    ? folders.find((folder) => folder.path === folderContextMenu.path)?.entries.filter((entry) => entry.type === 'pdf' || entry.type === 'md').length ?? 0
    : 0;

  useEffect(() => {
    if (!folderContextMenu) return;
    folderContextMenuFirstActionRef.current?.focus();

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setFolderContextMenu(null);
        folderContextMenuTriggerRef.current?.focus();
        return;
      }
      if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return;

      const menu = document.querySelector('.folderContextMenu');
      const actions = [...(menu?.querySelectorAll<HTMLButtonElement>('button') ?? [])];
      if (actions.length === 0) return;
      event.preventDefault();
      const current = document.activeElement;
      const currentIndex = actions.indexOf(current as HTMLButtonElement);
      const nextIndex = event.key === 'Home'
        ? 0
        : event.key === 'End'
          ? actions.length - 1
          : (currentIndex + (event.key === 'ArrowDown' ? 1 : -1) + actions.length) % actions.length;
      actions[nextIndex].focus();
    }

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [folderContextMenu]);

  useEffect(() => {
    if (!entryContextMenu) return;
    entryContextMenuActionRef.current?.focus();

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key !== 'Escape') return;
      setEntryContextMenu(null);
      entryContextMenuTriggerRef.current?.focus();
    }

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [entryContextMenu]);

  // Windows Explorer-style: Escape clears file selection while Explorer has focus,
  // but only after menus/modals have already had a chance to consume Escape.
  useEffect(() => {
    if (folderContextMenu || entryContextMenu || escapeBlocked) return;

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key !== 'Escape' || event.defaultPrevented) return;
      const active = document.activeElement;
      if (!(active instanceof HTMLElement)) return;
      if (active.closest('input, textarea, select, [contenteditable="true"]')) return;
      if (!active.closest('.sidePanel')) return;
      if (onClearFileSelection()) {
        event.preventDefault();
      }
    }

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [
    folderContextMenu,
    entryContextMenu,
    escapeBlocked,
    onClearFileSelection,
  ]);

  function applyExplorerFileFilter(filter: ExplorerFileFilter) {
    onFileFilterChange(filter);
    const current = fileSelectionRef.current;
    const next = pruneExplorerSelectionForFilter(
      [...current.selectedFiles, ...current.selectedPdfs],
      filter,
      current.selectionAnchorPath,
    );
    const partitioned = partitionExplorerSelection(next.selected);
    if (next.selected.length === 0) {
      fileSelectionRef.current = {
        selectedFiles: [],
        selectedPdfs: [],
        selectionAnchorPath: next.anchor,
      };
      onClearFileSelection();
      return;
    }
    commitFileSelection({
      selectedFiles: partitioned.vera,
      selectedPdfs: convertibleSelection(partitioned),
      selectionAnchorPath: next.anchor,
      explorerSelection: explorerSelection?.kind !== 'file'
        ? explorerSelection
        : explorerFileMatchesFilter(explorerSelection.type, filter) ? explorerSelection : null,
    });
  }

  function commitFromFileList(entry: FolderEntry, next: { selected: string[]; anchor: string | null }) {
    const partitioned = partitionExplorerSelection(next.selected);
    if (next.selected.length === 0) {
      fileSelectionRef.current = {
        selectedFiles: [],
        selectedPdfs: [],
        selectionAnchorPath: next.anchor,
      };
      onClearFileSelection();
      return;
    }
    commitFileSelection({
      selectedFiles: partitioned.vera,
      selectedPdfs: convertibleSelection(partitioned),
      selectionAnchorPath: next.anchor,
      explorerSelection: explorerSelectionAfterFileList({
        selectedVera: partitioned.vera,
        selectedPdf: partitioned.pdf,
        clickedPath: entry.path,
        clickedType: entry.type,
        activeLibraryPath,
      }),
    });
    // Keep the library path as Search/Ask fallback so deselecting a file does
    // not leave that file looking (and acting) like the current document.
    if (entry.type === 'vera' && partitioned.vera.length > 0 && !activeLibraryPath) {
      onUpdateTargetPath(entry.path);
    }
  }

  function selectExplorerEntry(entry: FolderEntry, event: { ctrlKey?: boolean; metaKey?: boolean; shiftKey?: boolean } = {}) {
    const current = fileSelectionRef.current;
    const visiblePaths = visibleExplorerFiles.map((item) => item.path);
    commitFromFileList(entry, applyFileListSelection({
      visiblePaths,
      selected: [...current.selectedFiles, ...current.selectedPdfs],
      anchor: current.selectionAnchorPath,
      clicked: entry.path,
      event,
    }));
  }

  function applyExplorerCheckbox(entry: FolderEntry, checked: boolean, shiftKey: boolean) {
    const current = fileSelectionRef.current;
    const visiblePaths = visibleExplorerFiles.map((item) => item.path);
    commitFromFileList(entry, applyFileListCheckbox({
      visiblePaths,
      selected: [...current.selectedFiles, ...current.selectedPdfs],
      anchor: current.selectionAnchorPath,
      clicked: entry.path,
      checked,
      shiftKey,
    }));
  }

  function toggleFolderCollapsed(folderPath: string) {
    onCollapsedFoldersChange((prev) =>
      prev.includes(folderPath) ? prev.filter((p) => p !== folderPath) : [...prev, folderPath],
    );
  }

  function showFolderContextMenu(folderPath: string, x: number, y: number) {
    folderContextMenuTriggerRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setFolderContextMenu({
      path: folderPath,
      x: Math.max(8, Math.min(x, window.innerWidth - 220)),
      y: Math.max(8, Math.min(y, window.innerHeight - 220)),
    });
  }

  function showEntryContextMenu(entry: FolderEntry, folderPath: string, x: number, y: number) {
    entryContextMenuTriggerRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setEntryContextMenu({
      entry,
      folderPath,
      x: Math.max(8, Math.min(x, window.innerWidth - 220)),
      y: Math.max(8, Math.min(y, window.innerHeight - 180)),
    });
  }

  const menus = (
    <>
      {folderContextMenu ? (
        <div className="folderContextMenuBackdrop" onClick={() => setFolderContextMenu(null)}>
          <div
            className="folderContextMenu"
            role="menu"
            style={{ left: folderContextMenu.x, top: folderContextMenu.y }}
            onClick={(event) => event.stopPropagation()}
          >
            <button
              ref={folderContextMenuFirstActionRef}
              role="menuitem"
              disabled={convertLocked || folderMenuSourceCount === 0}
              title={
                convertLocked
                  ? 'Wait for conversion to finish'
                  : folderMenuSourceCount === 0
                    ? 'No PDF or Markdown files in this folder'
                    : 'Open Convert for every PDF or Markdown file in this folder'
              }
              onClick={() => {
                onConvertFolder(folderContextMenu.path);
                setFolderContextMenu(null);
              }}
            >
              Convert{folderMenuSourceCount > 0 ? ` (${folderMenuSourceCount})` : ''}…
            </button>
            <button
              role="menuitem"
              disabled={Boolean(indexingFolders[folderContextMenu.path])}
              onClick={() => {
                void onManageIndex(folderContextMenu.path);
                setFolderContextMenu(null);
              }}
            >
              {indexingFolders[folderContextMenu.path]
                ? 'Indexing…'
                : indexStatuses[folderContextMenu.path]?.exists ? 'Update index' : 'Build index'}
            </button>
            <button
              role="menuitem"
              onClick={() => {
                void onRefreshFolder(folderContextMenu.path);
                setFolderContextMenu(null);
              }}
            >
              Rescan folder
            </button>
            <button
              role="menuitem"
              onClick={() => {
                void onRevealInFolder(folderContextMenu.path);
                setFolderContextMenu(null);
              }}
            >
              {showInFolderLabel(window.vera.platform)}
            </button>
            <div className="folderContextMenuSeparator" role="separator" />
            <button
              className="danger"
              role="menuitem"
              onClick={() => {
                onRemoveFolder(folderContextMenu.path);
                setFolderContextMenu(null);
              }}
            >
              Close folder
            </button>
          </div>
        </div>
      ) : null}
      {entryContextMenu ? (
        <div className="folderContextMenuBackdrop" onClick={() => setEntryContextMenu(null)}>
          <div
            className="folderContextMenu"
            role="menu"
            style={{ left: entryContextMenu.x, top: entryContextMenu.y }}
            onClick={(event) => event.stopPropagation()}
          >
            {entryContextMenu.entry.type === 'vera' || entryContextMenu.entry.type === 'pdf' || entryContextMenu.entry.type === 'md' ? (
              <button
                ref={entryContextMenuActionRef}
                role="menuitem"
                disabled={sourceLoading}
                title={sourceLoading ? `Waiting for ${fileName(pendingSourcePath)} to finish loading` : undefined}
                onClick={() => {
                  void onPreview(entryContextMenu.entry);
                  setEntryContextMenu(null);
                }}
              >
                {entryContextMenu.entry.type === 'vera' ? 'Preview embedded source' : 'View in document viewer'}
              </button>
            ) : null}
            {entryContextMenu.entry.type === 'vera' ? (
              <button
                role="menuitem"
                disabled={convertLocked}
                title={convertLocked ? 'Wait for reconvert preparation or conversion to finish' : 'Open Convert to replace this archive with a different parser or embedding'}
                onClick={() => {
                  const { entry, folderPath } = entryContextMenu;
                  setEntryContextMenu(null);
                  void onReconvert(entry, folderPath);
                }}
              >
                Reconvert…
              </button>
            ) : null}
            {entryContextMenu.entry.type === 'pdf' || entryContextMenu.entry.type === 'md' ? (
              <button
                role="menuitem"
                onClick={() => {
                  const entry = entryContextMenu.entry;
                  const paths = selectedPdfs.includes(entry.path) && selectedPdfs.length > 0
                    ? selectedPdfs
                    : [entry.path];
                  onConvertSelected(paths);
                  setEntryContextMenu(null);
                }}
              >
                Convert {
                  selectedPdfs.includes(entryContextMenu.entry.path) && selectedPdfs.length > 1
                    ? `files (${selectedPdfs.length})`
                    : 'file'
                }
              </button>
            ) : null}
            <button
              ref={entryContextMenu.entry.type === 'vera' || entryContextMenu.entry.type === 'pdf' || entryContextMenu.entry.type === 'md' ? undefined : entryContextMenuActionRef}
              role="menuitem"
              onClick={() => {
                void onRevealInFolder(entryContextMenu.entry.path);
                setEntryContextMenu(null);
              }}
            >
              {showInFolderLabel(window.vera.platform)}
            </button>
            <div className="folderContextMenuSeparator" role="separator" />
            <button
              className="danger"
              role="menuitem"
              onClick={() => {
                void onTrashEntry(entryContextMenu.entry, entryContextMenu.folderPath);
                setEntryContextMenu(null);
              }}
            >
              Move to Recycle Bin
            </button>
          </div>
        </div>
      ) : null}
    </>
  );

  return (
    <>
      {folders.length === 0 ? (
        <div className="sideEmpty">
          <Folder size={28} />
          <p>No folders open yet.</p>
          <button className="sidePrimary" onClick={() => void onAddFolder()}><FolderOpen size={15} />Open Folder</button>
        </div>
      ) : (
        <>
          <div className="explorerFileFilter" role="group" aria-label="Filter explorer files">
            {([
              ['all', 'All'],
              ['vera', 'VERA'],
              ['pdf', 'PDFs'],
              ['md', 'Markdown'],
            ] as const).map(([filter, label]) => (
              <button
                type="button"
                key={filter}
                className={explorerFileFilter === filter ? 'active' : ''}
                onClick={() => applyExplorerFileFilter(filter)}
                aria-pressed={explorerFileFilter === filter}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="explorerTree">
            {folders.map((folder) => {
            const visibleEntries = explorerFileFilter === 'all'
              ? folder.entries
              : folder.entries.filter((entry) => entry.type === explorerFileFilter);
            const folderIndex = indexStatuses[folder.path];
            const folderIndexChecking = Boolean(indexStatusChecking[folder.path]);
            const folderBusy = busyFolderPath === folder.path;
            const folderIndexing = indexingFolders[folder.path];
            const folderIndexReport = indexReports[folder.path];
            const indexBadgeClass = folderIndexing
              ? 'indexing'
              : folderIndexChecking && !folderIndex
                ? 'checking'
              : folderIndexReport?.skipped
                ? 'warning'
                : folderIndex?.fresh
                  ? 'fresh'
                  : folderIndex?.exists ? 'stale' : 'missing';
            const indexBadgeTitle = folderIndexing
              ? `${folderIndexing === 'build' ? 'Building' : 'Updating'} library index in the background`
              : folderIndexChecking && !folderIndex
                ? 'Checking index status…'
              : folderIndexReport?.skipped
                ? `Indexed with ${folderIndexReport.skipped} skipped archive(s). Select for details.`
                : folderIndex?.fresh
                  ? `${folderIndexReport ? 'Indexed. Select for the latest build report.' : 'Indexed'}${folderIndexChecking ? ' Verifying current folder state…' : ''}`
                  : folderIndex?.exists
                    ? `Index needs updating: ${folderIndex.reasons.join('; ')}${folderIndexChecking ? ' Verifying current folder state…' : ''}`
                    : 'No index';
            return (
            <section
              className={activeLibraryPath === folder.path
                ? selectedFiles.length > 0 ? 'folderGroup' : 'folderGroup activeLibrary'
                : 'folderGroup'}
              key={folder.path}
            >
              <div
                className="folderGroupHead"
                title={folder.path}
                onContextMenu={(event) => {
                  event.preventDefault();
                  showFolderContextMenu(folder.path, event.clientX, event.clientY);
                }}
              >
                <button
                  className="folderCollapseAction"
                  onClick={() => toggleFolderCollapsed(folder.path)}
                  title={folderBusy ? busyAction || 'Working…' : collapsedFolders.includes(folder.path) ? 'Expand' : 'Collapse'}
                >
                  <span className={folderBusy ? 'folderToggleIcon loading' : 'folderToggleIcon'}>
                    {folderBusy ? (
                      <RefreshCw size={14} className="folderStateIcon spinning" aria-hidden="true" />
                    ) : (
                      <>
                        {collapsedFolders.includes(folder.path) ? <Folder size={14} className="folderStateIcon" /> : <FolderOpen size={14} className="folderStateIcon" />}
                        {collapsedFolders.includes(folder.path) ? <ChevronRight size={14} className="folderCaretIcon" /> : <ChevronDown size={14} className="folderCaretIcon" />}
                      </>
                    )}
                  </span>
                </button>
                <button
                  className="folderGroupToggle"
                  onClick={() => onSelectFolder(folder.path)}
                  onDoubleClick={() => void onOpenLibraryInfo(folder.path)}
                  onKeyDown={(event) => {
                    if (event.key !== 'ContextMenu' && !(event.shiftKey && event.key === 'F10')) return;
                    event.preventDefault();
                    const bounds = event.currentTarget.getBoundingClientRect();
                    showFolderContextMenu(folder.path, bounds.left, bounds.bottom);
                  }}
                  title="Use as active library · double-click for Library Info"
                  aria-haspopup="menu"
                  aria-expanded={folderContextMenu?.path === folder.path}
                >
                  <span className="folderGroupName">{folder.name}</span>
                </button>
                <button
                  type="button"
                  className={`indexBadge ${indexBadgeClass}`}
                  title={indexBadgeTitle}
                  aria-label={`Index status: ${folderIndexing ? 'indexing' : folderIndexChecking && !folderIndex ? 'checking' : folderIndexReport?.skipped ? `indexed with ${folderIndexReport.skipped} skipped` : folderIndex?.fresh ? 'indexed' : folderIndex?.exists ? 'needs updating' : 'no index'}`}
                  disabled={Boolean(folderIndexing) || !folderIndexReport}
                  onClick={() => {
                    if (!folderIndexReport) return;
                    onShowIndexReport(folderIndexReport);
                  }}
                >
                  {folderIndexing
                    ? <RefreshCw size={11} className="spinning" aria-hidden="true" />
                    : folderIndexChecking && !folderIndex
                      ? <RefreshCw size={11} className="spinning" aria-hidden="true" />
                    : folderIndexReport?.skipped
                      ? <AlertTriangle size={11} aria-hidden="true" />
                      : <Database size={11} aria-hidden="true" />}
                </button>
              </div>
              {collapsedFolders.includes(folder.path) ? null : visibleEntries.length === 0 ? (
                <p className="folderEmpty">
                  {explorerFileFilter === 'all'
                    ? 'No .vera, .pdf, or .md files'
                    : `No .${explorerFileFilter} files`}
                </p>
              ) : (
                visibleEntries.map((entry) => {
                  const listed = selectedFiles.includes(entry.path) || selectedPdfs.includes(entry.path);
                  const previewing = pendingSourcePath === entry.path || sourceDocumentPath === entry.path;
                  const scopedDocument = !activeLibraryPath
                    && selectedFiles.length === 0
                    && selectedPdfs.length === 0
                    && path === entry.path;
                  const tone = explorerRowTone({ selected: listed, previewing, scopedDocument });
                  const rowClass = tone === 'idle'
                    ? 'fileRow'
                    : tone === 'preview' ? 'fileRow previewing' : 'fileRow active';
                  return (
                  <div
                    key={entry.path}
                    className="fileRowWrap"
                    onClick={(event) => {
                      const origin = event.target;
                      if (origin instanceof Element && origin.closest('.fileRowCheck, .fileRow')) return;
                      selectExplorerEntry(entry, event);
                    }}
                  >
                    <input
                      type="checkbox"
                      className="fileRowCheck"
                      checked={listed}
                      onClick={(event) => event.stopPropagation()}
                      onChange={(event) => {
                        event.stopPropagation();
                        const shiftKey = 'shiftKey' in event.nativeEvent
                          && Boolean((event.nativeEvent as MouseEvent).shiftKey);
                        applyExplorerCheckbox(entry, event.target.checked, shiftKey);
                      }}
                      title={entry.type === 'vera' ? 'Add or remove from search scope' : 'Add or remove from Convert selection'}
                    />
                    <button
                      className={rowClass}
                      aria-selected={listed || scopedDocument}
                      onClick={(event) => selectExplorerEntry(entry, event)}
                      onDoubleClick={() => {
                        if (entry.type === 'vera' || entry.type === 'pdf' || entry.type === 'md') {
                          void onPreview(entry);
                        }
                      }}
                      onContextMenu={(event) => {
                        event.preventDefault();
                        showEntryContextMenu(entry, folder.path, event.clientX, event.clientY);
                      }}
                      title={
                        sourceLoading
                          ? `${entry.relativePath} — loading ${fileName(pendingSourcePath)}…`
                          : `${entry.relativePath} — click to select · Ctrl/Cmd+click to add or remove · Shift+click a range · click empty space or Esc to clear · double-click to preview`
                      }
                    >
                      {entry.type === 'vera' ? <VeraIcon size={14} className="fileRowIcon vera" /> : <FileText size={14} className="fileRowIcon pdf" />}
                      <span className="fileRowName">{entry.relativePath}</span>
                    </button>
                  </div>
                  );
                })
              )}
            </section>
            );
            })}
          </div>
        </>
      )}
      {createPortal(menus, document.body)}
    </>
  );
}
