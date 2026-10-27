import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { createPortal } from 'react-dom';
import {
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Database,
  FileText,
  Folder,
  FolderOpen,
  Library,
  Plus,
  RefreshCw,
} from 'lucide-react';
import { VeraIcon } from './VeraIcon';
import {
  applyFileListCheckbox,
  applyFileListSelection,
  buildExplorerTree,
  explorerFileMatchesFilter,
  explorerRowTone,
  explorerSelectionAfterFileList,
  filterExplorerTree,
  partitionExplorerSelection,
  convertibleSelection,
  persistExpandedSubfolders,
  pruneExplorerSelectionForFilter,
  readExpandedSubfolders,
  visibleExplorerDocuments,
  type ExplorerDocument,
  type ExplorerFileFilter,
  type ExplorerTreeFolder,
} from '../lib/explorer';
import { fileName, isPathInsideFolder, showInFolderLabel, type ExplorerSelection } from '../lib/formatting';
import type {
  FolderEntry,
  LibraryIndexBuildReport,
  LibraryIndexStatus,
  WorkspaceFolderResult,
} from '../types';

type TreeFolder = ExplorerTreeFolder<FolderEntry>;
type TreeDocument = ExplorerDocument<FolderEntry>;

type ExplorerMenu =
  | { kind: 'root'; path: string; x: number; y: number }
  | { kind: 'subfolder'; folder: TreeFolder; rootPath: string; x: number; y: number }
  | { kind: 'document'; doc: TreeDocument; folderPath: string; x: number; y: number };

export type ExplorerFileSelection = {
  selectedFiles: string[];
  selectedPdfs: string[];
  selectionAnchorPath: string | null;
  explorerSelection: ExplorerSelection | null;
};

const FILTERS = [
  ['all', 'All'],
  ['ready', 'Ready'],
  ['pending', 'To convert'],
] as const;

export function ExplorerPanel({
  folders,
  libraryPaths,
  activeLibraryPath,
  folderScopePath,
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
  onAddLibrary,
  onAddFolder,
  onFileFilterChange,
  onCollapsedFoldersChange,
  onFileSelectionChange,
  onSelectFolder,
  onSearchFolder,
  onOpenLibraryInfo,
  onUpdateTargetPath,
  onPreview,
  onShowIndexReport,
  onConvertFolder,
  onConvertSelected,
  onConvertFolderWithOptions,
  onConvertSelectedWithOptions,
  onReconvert,
  onManageIndex,
  onRefreshFolder,
  onRevealInFolder,
  onMakeLibrary,
  onMakeFolder,
  onRemoveFolder,
  onTrashEntry,
}: {
  folders: WorkspaceFolderResult[];
  libraryPaths: string[];
  activeLibraryPath: string;
  /** Subfolder of the active library that Search and Ask are limited to, or ''. */
  folderScopePath: string;
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
  onAddLibrary: () => void;
  onAddFolder: () => void;
  onFileFilterChange: (filter: ExplorerFileFilter) => void;
  onCollapsedFoldersChange: (update: (prev: string[]) => string[]) => void;
  onFileSelectionChange: (next: ExplorerFileSelection) => void;
  onSelectFolder: (folderPath: string) => void;
  onSearchFolder: (libraryPath: string, folderPath: string) => void;
  onOpenLibraryInfo: (folderPath: string) => void;
  onUpdateTargetPath: (value: string) => void;
  onPreview: (entry: FolderEntry) => void;
  onShowIndexReport: (report: LibraryIndexBuildReport) => void;
  /** Start converting right away with the saved defaults. */
  onConvertFolder: (folderPath: string) => void;
  onConvertSelected: (paths: string[]) => void;
  /** Open the Convert view with this target filled in. */
  onConvertFolderWithOptions: (folderPath: string) => void;
  onConvertSelectedWithOptions: (paths: string[]) => void;
  onReconvert: (entry: FolderEntry, folderPath: string) => void;
  onManageIndex: (folderPath: string) => void;
  onRefreshFolder: (folderPath: string) => void;
  onRevealInFolder: (targetPath: string) => void;
  onMakeLibrary: (folderPath: string) => void;
  onMakeFolder: (folderPath: string) => void;
  onRemoveFolder: (folderPath: string) => void;
  onTrashEntry: (entry: FolderEntry, folderPath: string) => void;
}) {
  const [menu, setMenu] = useState<ExplorerMenu | null>(null);
  const menuTriggerRef = useRef<HTMLElement | null>(null);
  const [expandedSubfolders, setExpandedSubfolders] = useState(readExpandedSubfolders);

  const trees = useMemo(
    () => folders.map((folder) => {
      const full = buildExplorerTree(folder);
      return { folder, full, visible: filterExplorerTree(full, explorerFileFilter) };
    }),
    [folders, explorerFileFilter],
  );
  const visibleDocuments = useMemo(
    () => visibleExplorerDocuments(trees.map((tree) => tree.visible), collapsedFolders, expandedSubfolders),
    [trees, collapsedFolders, expandedSubfolders],
  );
  const libraryTrees = trees.filter((tree) => libraryPaths.includes(tree.folder.path));
  const plainTrees = trees.filter((tree) => !libraryPaths.includes(tree.folder.path));

  // Reveal the scoped folder's row, which may sit under collapsed subfolders.
  useEffect(() => {
    if (!folderScopePath) return;
    const root = trees.find((tree) => isPathInsideFolder(folderScopePath, tree.folder.path));
    if (!root) return;
    const ancestors: string[] = [];
    const walk = (folder: TreeFolder) => {
      for (const child of folder.folders) {
        if (child.path !== folderScopePath && isPathInsideFolder(folderScopePath, child.path)) {
          ancestors.push(child.path);
          walk(child);
        }
      }
    };
    walk(root.full);
    onCollapsedFoldersChange((prev) => (
      prev.includes(root.folder.path) ? prev.filter((entry) => entry !== root.folder.path) : prev
    ));
    if (!ancestors.length) return;
    setExpandedSubfolders((prev) => {
      const missing = ancestors.filter((entry) => !prev.includes(entry));
      if (!missing.length) return prev;
      const next = [...prev, ...missing];
      persistExpandedSubfolders(next);
      return next;
    });
    // Only re-run when the scope changes, not on every folder rescan.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [folderScopePath]);

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

  useEffect(() => {
    if (!menu) return;
    document.querySelector<HTMLButtonElement>('.folderContextMenu button:not(:disabled)')?.focus();

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setMenu(null);
        menuTriggerRef.current?.focus();
        return;
      }
      if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return;

      const menuElement = document.querySelector('.folderContextMenu');
      const actions = [...(menuElement?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)') ?? [])];
      if (actions.length === 0) return;
      event.preventDefault();
      const currentIndex = actions.indexOf(document.activeElement as HTMLButtonElement);
      const nextIndex = event.key === 'Home'
        ? 0
        : event.key === 'End'
          ? actions.length - 1
          : (currentIndex + (event.key === 'ArrowDown' ? 1 : -1) + actions.length) % actions.length;
      actions[nextIndex].focus();
    }

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [menu]);

  // Windows Explorer-style: Escape clears file selection while Explorer has focus,
  // but only after menus/modals have already had a chance to consume Escape.
  useEffect(() => {
    if (menu || escapeBlocked) return;

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
  }, [menu, escapeBlocked, onClearFileSelection]);

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

  function commitFromFileList(doc: TreeDocument, next: { selected: string[]; anchor: string | null }) {
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
        clickedPath: doc.path,
        clickedType: doc.type,
        activeLibraryPath,
      }),
    });
    // Keep the library path as Search/Ask fallback so deselecting a file does
    // not leave that file looking (and acting) like the current document.
    if (doc.type === 'vera' && partitioned.vera.length > 0 && !activeLibraryPath) {
      onUpdateTargetPath(doc.path);
    }
  }

  function selectDocument(doc: TreeDocument, event: { ctrlKey?: boolean; metaKey?: boolean; shiftKey?: boolean } = {}) {
    const current = fileSelectionRef.current;
    commitFromFileList(doc, applyFileListSelection({
      visiblePaths: visibleDocuments.map((item) => item.path),
      selected: [...current.selectedFiles, ...current.selectedPdfs],
      anchor: current.selectionAnchorPath,
      clicked: doc.path,
      event,
    }));
  }

  function applyDocumentCheckbox(doc: TreeDocument, checked: boolean, shiftKey: boolean) {
    const current = fileSelectionRef.current;
    commitFromFileList(doc, applyFileListCheckbox({
      visiblePaths: visibleDocuments.map((item) => item.path),
      selected: [...current.selectedFiles, ...current.selectedPdfs],
      anchor: current.selectionAnchorPath,
      clicked: doc.path,
      checked,
      shiftKey,
    }));
  }

  function toggleFolderCollapsed(folderPath: string) {
    onCollapsedFoldersChange((prev) =>
      prev.includes(folderPath) ? prev.filter((p) => p !== folderPath) : [...prev, folderPath],
    );
  }

  function toggleSubfolder(folderPath: string) {
    setExpandedSubfolders((prev) => {
      const next = prev.includes(folderPath) ? prev.filter((p) => p !== folderPath) : [...prev, folderPath];
      persistExpandedSubfolders(next);
      return next;
    });
  }

  function showMenu(next: ExplorerMenu) {
    menuTriggerRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setMenu({
      ...next,
      x: Math.max(8, Math.min(next.x, window.innerWidth - 220)),
      y: Math.max(8, Math.min(next.y, window.innerHeight - 240)),
    });
  }

  function runMenuAction(action: () => void) {
    setMenu(null);
    action();
  }

  function convertMenuItems(folderPath: string, sourceCount: number, pending: number) {
    const lockedTitle = convertLocked ? 'Wait for conversion to finish' : undefined;
    return (
      <>
        <button
          role="menuitem"
          disabled={convertLocked || pending === 0}
          title={lockedTitle ?? (pending === 0 ? 'Everything here is converted' : 'Convert new files now with your default settings')}
          onClick={() => runMenuAction(() => onConvertFolder(folderPath))}
        >
          {pending > 0 ? `Convert ${pending} new file${pending === 1 ? '' : 's'}` : 'Convert'}
        </button>
        <button
          role="menuitem"
          disabled={convertLocked || sourceCount === 0}
          title={lockedTitle ?? 'Open Convert for this folder to change settings or replace existing archives'}
          onClick={() => runMenuAction(() => onConvertFolderWithOptions(folderPath))}
        >
          Convert with options…
        </button>
      </>
    );
  }

  function menuItems(current: ExplorerMenu) {
    if (current.kind === 'root') {
      const tree = trees.find((item) => item.folder.path === current.path)?.full;
      const isLibrary = libraryPaths.includes(current.path);
      const sourceCount = (tree?.readyCount ?? 0) + (tree?.pendingCount ?? 0);
      const pending = tree?.pendingCount ?? 0;
      return (
        <>
          {convertMenuItems(current.path, sourceCount, pending)}
          {isLibrary ? (
            <button
              role="menuitem"
              disabled={Boolean(indexingFolders[current.path])}
              onClick={() => runMenuAction(() => onManageIndex(current.path))}
            >
              {indexingFolders[current.path]
                ? 'Indexing…'
                : indexStatuses[current.path]?.exists ? 'Update index' : 'Build index'}
            </button>
          ) : (
            <button
              role="menuitem"
              title="Search this folder as a whole and keep a fast index for it"
              onClick={() => runMenuAction(() => onMakeLibrary(current.path))}
            >
              Make this a library
            </button>
          )}
          <button role="menuitem" onClick={() => runMenuAction(() => onRefreshFolder(current.path))}>
            Rescan folder
          </button>
          <button role="menuitem" onClick={() => runMenuAction(() => onRevealInFolder(current.path))}>
            {showInFolderLabel(window.vera.platform)}
          </button>
          <div className="folderContextMenuSeparator" role="separator" />
          {isLibrary ? (
            <button
              role="menuitem"
              title="Keep this folder open, but stop treating it as a library"
              onClick={() => runMenuAction(() => onMakeFolder(current.path))}
            >
              Remove from Libraries
            </button>
          ) : null}
          <button className="danger" role="menuitem" onClick={() => runMenuAction(() => onRemoveFolder(current.path))}>
            {isLibrary ? 'Close library' : 'Close folder'}
          </button>
        </>
      );
    }

    if (current.kind === 'subfolder') {
      const pending = current.folder.pendingCount;
      const inLibrary = libraryPaths.includes(current.rootPath);
      const scoped = folderScopePath === current.folder.path;
      return (
        <>
          {inLibrary ? (
            <button
              role="menuitem"
              disabled={!scoped && current.folder.readyCount === 0}
              title={!scoped && current.folder.readyCount === 0
                ? 'Convert files in this folder before searching it'
                : scoped
                  ? 'Search and Ask use the whole library again'
                  : 'Search and Ask only use documents in this folder and its subfolders'}
              onClick={() => runMenuAction(() => (
                scoped ? onSelectFolder(current.rootPath) : onSearchFolder(current.rootPath, current.folder.path)
              ))}
            >
              {scoped ? 'Search whole library' : 'Search this folder'}
            </button>
          ) : null}
          {convertMenuItems(current.folder.path, current.folder.readyCount + pending, pending)}
          <button role="menuitem" onClick={() => runMenuAction(() => onRevealInFolder(current.folder.path))}>
            {showInFolderLabel(window.vera.platform)}
          </button>
        </>
      );
    }

    const { doc, folderPath } = current;
    const primary = (doc.archive ?? doc.source) as FolderEntry;
    const convertPaths = selectedPdfs.includes(doc.path) && selectedPdfs.length > 0 ? selectedPdfs : [doc.path];
    return (
      <>
        <button
          role="menuitem"
          disabled={sourceLoading}
          title={sourceLoading ? `Waiting for ${fileName(pendingSourcePath)} to finish loading` : undefined}
          onClick={() => runMenuAction(() => onPreview(primary))}
        >
          {doc.archive ? 'Preview document' : 'View in document viewer'}
        </button>
        {doc.archive ? (
          <button
            role="menuitem"
            disabled={convertLocked}
            title={convertLocked ? 'Wait for reconvert preparation or conversion to finish' : 'Open Convert to replace this archive with a different parser or embedding'}
            onClick={() => runMenuAction(() => onReconvert(doc.archive as FolderEntry, folderPath))}
          >
            Reconvert…
          </button>
        ) : (
          <>
            <button
              role="menuitem"
              disabled={convertLocked}
              title={convertLocked ? 'Wait for conversion to finish' : 'Convert now with your default settings'}
              onClick={() => runMenuAction(() => onConvertSelected(convertPaths))}
            >
              Convert {convertPaths.length > 1 ? `${convertPaths.length} files` : 'file'}
            </button>
            <button
              role="menuitem"
              disabled={convertLocked}
              onClick={() => runMenuAction(() => onConvertSelectedWithOptions(convertPaths))}
            >
              Convert with options…
            </button>
          </>
        )}
        <button role="menuitem" onClick={() => runMenuAction(() => onRevealInFolder(primary.path))}>
          {showInFolderLabel(window.vera.platform)}
        </button>
        <div className="folderContextMenuSeparator" role="separator" />
        <button
          className="danger"
          role="menuitem"
          title={doc.archive && doc.source ? `Keeps ${doc.source.name}` : undefined}
          onClick={() => runMenuAction(() => onTrashEntry(primary, folderPath))}
        >
          {doc.archive && doc.source ? 'Move .vera to Recycle Bin' : 'Move to Recycle Bin'}
        </button>
      </>
    );
  }

  const menus = menu ? (
    <div className="folderContextMenuBackdrop" onClick={() => setMenu(null)}>
      <div
        className="folderContextMenu"
        role="menu"
        style={{ left: menu.x, top: menu.y }}
        onClick={(event) => event.stopPropagation()}
      >
        {menuItems(menu)}
      </div>
    </div>
  ) : null;

  function renderDocument(doc: TreeDocument, depth: number, folderPath: string) {
    const listed = selectedFiles.includes(doc.path) || selectedPdfs.includes(doc.path);
    const rowPaths = [doc.archive?.path, doc.source?.path];
    const previewing = rowPaths.includes(pendingSourcePath) || rowPaths.includes(sourceDocumentPath);
    const scopedDocument = !activeLibraryPath
      && selectedFiles.length === 0
      && selectedPdfs.length === 0
      && path === doc.path;
    const tone = explorerRowTone({ selected: listed, previewing, scopedDocument });
    const rowClass = [
      'fileRow',
      tone === 'preview' ? 'previewing' : tone === 'idle' ? '' : 'active',
      doc.archive ? '' : 'pending',
    ].filter(Boolean).join(' ');
    const primary = (doc.archive ?? doc.source) as FolderEntry;
    const described = doc.archive && doc.source
      ? `${doc.archive.relativePath} (source: ${doc.source.name})`
      : doc.archive ? doc.archive.relativePath : `${primary.relativePath} — not converted yet`;
    return (
      <div
        key={doc.path}
        className="fileRowWrap"
        style={{ '--depth': depth } as CSSProperties}
        onClick={(event) => {
          const origin = event.target;
          if (origin instanceof Element && origin.closest('.fileRowCheck, .fileRow')) return;
          selectDocument(doc, event);
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
            applyDocumentCheckbox(doc, event.target.checked, shiftKey);
          }}
          title={doc.archive ? 'Add or remove from search scope' : 'Add or remove from Convert selection'}
        />
        <button
          className={rowClass}
          aria-selected={listed || scopedDocument}
          onClick={(event) => selectDocument(doc, event)}
          onDoubleClick={() => { void onPreview(primary); }}
          onContextMenu={(event) => {
            event.preventDefault();
            showMenu({ kind: 'document', doc, folderPath, x: event.clientX, y: event.clientY });
          }}
          title={
            sourceLoading
              ? `${described} — loading ${fileName(pendingSourcePath)}…`
              : `${described} — click to select · Ctrl/Cmd+click to add or remove · Shift+click a range · click empty space or Esc to clear · double-click to preview`
          }
        >
          {doc.archive
            ? <VeraIcon size={14} className="fileRowIcon vera" />
            : <FileText size={14} className={`fileRowIcon ${doc.type}`} />}
          <span className="fileRowName">{doc.label}</span>
        </button>
      </div>
    );
  }

  function renderFolderContents(folder: TreeFolder, depth: number, rootPath: string) {
    return (
      <>
        {folder.folders.map((child) => {
          const expanded = expandedSubfolders.includes(child.path);
          return (
            <div className="subfolderGroup" key={child.path}>
              <button
                type="button"
                className={folderScopePath === child.path ? 'subfolderRow scoped' : 'subfolderRow'}
                style={{ '--depth': depth } as CSSProperties}
                aria-expanded={expanded}
                title={child.relativePath}
                onClick={() => toggleSubfolder(child.path)}
                onContextMenu={(event) => {
                  event.preventDefault();
                  showMenu({ kind: 'subfolder', folder: child, rootPath, x: event.clientX, y: event.clientY });
                }}
                onKeyDown={(event) => {
                  if (event.key !== 'ContextMenu' && !(event.shiftKey && event.key === 'F10')) return;
                  event.preventDefault();
                  const bounds = event.currentTarget.getBoundingClientRect();
                  showMenu({ kind: 'subfolder', folder: child, rootPath, x: bounds.left, y: bounds.bottom });
                }}
              >
                {expanded ? <ChevronDown size={12} className="subfolderCaret" /> : <ChevronRight size={12} className="subfolderCaret" />}
                {expanded ? <FolderOpen size={13} className="subfolderIcon" /> : <Folder size={13} className="subfolderIcon" />}
                <span className="subfolderName">{child.name}</span>
              </button>
              {expanded ? renderFolderContents(child, depth + 1, rootPath) : null}
            </div>
          );
        })}
        {folder.documents.map((doc) => renderDocument(doc, depth, rootPath))}
      </>
    );
  }

  function renderRoot({ folder, full, visible }: (typeof trees)[number]) {
    const isLibrary = libraryPaths.includes(folder.path);
    const collapsed = collapsedFolders.includes(folder.path);
    const folderBusy = busyFolderPath === folder.path;
    const empty = visible.documents.length === 0 && visible.folders.length === 0;
    return (
      <section
        className={isLibrary && activeLibraryPath === folder.path && selectedFiles.length === 0
          ? 'folderGroup activeLibrary'
          : 'folderGroup'}
        key={folder.path}
      >
        <div
          className="folderGroupHead"
          title={folder.path}
          onContextMenu={(event) => {
            event.preventDefault();
            showMenu({ kind: 'root', path: folder.path, x: event.clientX, y: event.clientY });
          }}
        >
          <button
            className="folderCollapseAction"
            onClick={() => toggleFolderCollapsed(folder.path)}
            title={folderBusy ? busyAction || 'Working…' : collapsed ? 'Expand' : 'Collapse'}
          >
            <span className={folderBusy ? 'folderToggleIcon loading' : 'folderToggleIcon'}>
              {folderBusy ? (
                <RefreshCw size={14} className="folderStateIcon spinning" aria-hidden="true" />
              ) : (
                <>
                  {isLibrary
                    ? <Library size={14} className="folderStateIcon" />
                    : collapsed ? <Folder size={14} className="folderStateIcon" /> : <FolderOpen size={14} className="folderStateIcon" />}
                  {collapsed ? <ChevronRight size={14} className="folderCaretIcon" /> : <ChevronDown size={14} className="folderCaretIcon" />}
                </>
              )}
            </span>
          </button>
          <button
            className="folderGroupToggle"
            onClick={() => (isLibrary ? onSelectFolder(folder.path) : toggleFolderCollapsed(folder.path))}
            onDoubleClick={() => { if (isLibrary) void onOpenLibraryInfo(folder.path); }}
            onKeyDown={(event) => {
              if (event.key !== 'ContextMenu' && !(event.shiftKey && event.key === 'F10')) return;
              event.preventDefault();
              const bounds = event.currentTarget.getBoundingClientRect();
              showMenu({ kind: 'root', path: folder.path, x: bounds.left, y: bounds.bottom });
            }}
            title={isLibrary
              ? 'Search this library · double-click for Library Info'
              : 'Expand or collapse · check .vera files to search them · right-click to make this a library'}
            aria-haspopup="menu"
            aria-expanded={menu?.kind === 'root' && menu.path === folder.path}
          >
            <span className="folderGroupName">{folder.name}</span>
          </button>
          {isLibrary ? renderIndexBadge(folder.path) : null}
        </div>
        {collapsed ? null : empty ? (
          <p className="folderEmpty">
            {explorerFileFilter === 'all'
              ? 'No .vera, .pdf, or .md files'
              : explorerFileFilter === 'ready' ? 'No converted documents yet' : 'Everything here is converted'}
          </p>
        ) : renderFolderContents(visible, 0, folder.path)}
      </section>
    );
  }

  function renderIndexBadge(folderPath: string) {
    const folderIndex = indexStatuses[folderPath];
    const folderIndexChecking = Boolean(indexStatusChecking[folderPath]);
    const folderIndexing = indexingFolders[folderPath];
    const folderIndexReport = indexReports[folderPath];
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
        {folderIndexing || (folderIndexChecking && !folderIndex)
          ? <RefreshCw size={11} className="spinning" aria-hidden="true" />
          : folderIndexReport?.skipped
            ? <AlertTriangle size={11} aria-hidden="true" />
            : <Database size={11} aria-hidden="true" />}
      </button>
    );
  }

  return (
    <>
      {folders.length === 0 ? (
        <div className="sideEmpty">
          <Library size={28} />
          <p>No libraries yet.</p>
          <p className="sideEmptyHint">A library is a folder of documents you search together.</p>
          <button className="sidePrimary" onClick={() => void onAddLibrary()}><Library size={15} />Add Library</button>
          <button className="sideLink" onClick={() => void onAddFolder()}>Or open a folder without indexing it</button>
        </div>
      ) : (
        <>
          <div className="explorerFileFilter" role="group" aria-label="Filter explorer documents">
            {FILTERS.map(([filter, label]) => (
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
            <div className="explorerSection">
              <div className="explorerSectionHead">
                <span>Libraries</span>
                <button type="button" className="explorerSectionAction" onClick={() => void onAddLibrary()} title="Add library">
                  <Plus size={13} />
                </button>
              </div>
              {libraryTrees.length === 0 ? (
                <p className="explorerSectionHint">Add a library to search a whole folder of documents with a fast index.</p>
              ) : libraryTrees.map(renderRoot)}
            </div>
            {plainTrees.length > 0 ? (
              <div className="explorerSection">
                <div className="explorerSectionHead">
                  <span>Folders</span>
                  <button type="button" className="explorerSectionAction" onClick={() => void onAddFolder()} title="Open folder">
                    <Plus size={13} />
                  </button>
                </div>
                {plainTrees.map(renderRoot)}
              </div>
            ) : null}
          </div>
        </>
      )}
      {createPortal(menus, document.body)}
    </>
  );
}
