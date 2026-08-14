import type { ExplorerSelection } from './formatting';

/**
 * Keep Explorer scannable around the active library without fighting file
 * selection: expand the active library and collapse the rest when one is set;
 * when none is active (e.g. a single .vera is scoped), preserve the user's
 * expand/collapse state and only drop folders that are no longer open.
 * Startup should seed this from saved folder paths and the last active library
 * so Explorer does not paint every folder expanded first.
 */
export function syncCollapsedFolders(
  folderPaths: string[],
  activeLibraryPath: string,
  previousCollapsed: string[] = [],
): string[] {
  const active = activeLibraryPath.trim();
  if (!active) {
    // Selecting a document clears the active library. Keep the user's expanded
    // folders so the file they clicked stays visible.
    return previousCollapsed.filter((folderPath) => folderPaths.includes(folderPath));
  }
  return folderPaths.filter((folderPath) => folderPath !== active);
}

export type ExplorerFileFilter = 'all' | 'vera' | 'pdf';

export type ExplorerListEntry = {
  path: string;
  type: 'vera' | 'pdf';
};

export type FileListModifiers = {
  ctrlKey?: boolean;
  metaKey?: boolean;
  shiftKey?: boolean;
};

export type FileListSelection = {
  selected: string[];
  anchor: string | null;
};

export function explorerEntryType(path: string): 'vera' | 'pdf' | null {
  const lower = path.toLowerCase();
  if (lower.endsWith('.vera')) return 'vera';
  if (lower.endsWith('.pdf')) return 'pdf';
  return null;
}

/** File → Open Folder sends a directory; File → Open sends a `.vera` archive. */
export function isDirectoryOpenTarget(targetPath: string): boolean {
  const trimmed = targetPath.trim();
  return Boolean(trimmed) && !trimmed.toLowerCase().endsWith('.vera');
}

export function routeOpenTarget(
  targetPath: string,
  handlers: { addFolder: (path: string) => void; openFile: (path: string) => void },
): void {
  if (isDirectoryOpenTarget(targetPath)) handlers.addFolder(targetPath);
  else handlers.openFile(targetPath);
}

export function explorerFileMatchesFilter(
  type: 'vera' | 'pdf',
  filter: ExplorerFileFilter,
): boolean {
  return filter === 'all' || type === filter;
}

/** Drop hidden files from the Explorer selection when the type filter changes. */
export function pruneExplorerSelectionForFilter(
  selected: string[],
  filter: ExplorerFileFilter,
  anchor: string | null = null,
): FileListSelection {
  const next = filter === 'all'
    ? selected
    : selected.filter((path) => explorerEntryType(path) === filter);
  const nextAnchor = anchor && next.includes(anchor) ? anchor : null;
  return { selected: next, anchor: nextAnchor };
}

export function partitionExplorerSelection(paths: string[]): { vera: string[]; pdf: string[] } {
  const vera: string[] = [];
  const pdf: string[] = [];
  for (const path of paths) {
    const type = explorerEntryType(path);
    if (type === 'vera') vera.push(path);
    else if (type === 'pdf') pdf.push(path);
  }
  return { vera, pdf };
}

export function visibleExplorerEntries(
  folders: { path: string; entries: ExplorerListEntry[] }[],
  collapsedFolders: string[],
  filter: ExplorerFileFilter,
): ExplorerListEntry[] {
  const visible: ExplorerListEntry[] = [];
  for (const folder of folders) {
    if (collapsedFolders.includes(folder.path)) continue;
    for (const entry of folder.entries) {
      if (filter === 'all' || entry.type === filter) visible.push(entry);
    }
  }
  return visible;
}

function rangeInclusive(items: string[], from: string, to: string): string[] {
  const start = items.indexOf(from);
  const end = items.indexOf(to);
  if (start < 0 && end < 0) return [to];
  if (start < 0) return [to];
  if (end < 0) return [from];
  const lo = Math.min(start, end);
  const hi = Math.max(start, end);
  return items.slice(lo, hi + 1);
}

function isToggleModifier(event: FileListModifiers): boolean {
  return Boolean(event.ctrlKey || event.metaKey);
}

/**
 * Windows/macOS file-list selection against the currently visible rows.
 *
 * - click: select only the clicked row
 * - Ctrl/Cmd+click: toggle the clicked row
 * - Shift+click: select the inclusive range from the anchor
 * - Ctrl/Cmd+Shift+click: add that range to the current selection
 */
export function applyFileListSelection(options: {
  visiblePaths: string[];
  selected: string[];
  anchor: string | null;
  clicked: string;
  event: FileListModifiers;
}): FileListSelection {
  const { visiblePaths, selected, clicked, event } = options;
  const toggle = isToggleModifier(event);
  const shift = Boolean(event.shiftKey);
  const anchor = options.anchor
    && visiblePaths.includes(options.anchor)
    ? options.anchor
    : null;

  if (shift && anchor) {
    const range = rangeInclusive(visiblePaths, anchor, clicked);
    if (toggle) {
      const seen = new Set(selected);
      const next = [...selected];
      for (const path of range) {
        if (seen.has(path)) continue;
        seen.add(path);
        next.push(path);
      }
      return { selected: next, anchor };
    }
    return { selected: range, anchor };
  }

  if (toggle) {
    const next = selected.includes(clicked)
      ? selected.filter((path) => path !== clicked)
      : [...selected, clicked];
    return { selected: next, anchor: clicked };
  }

  return { selected: [clicked], anchor: clicked };
}

/**
 * Checkbox membership is explicit (`checked`), not a Ctrl-toggle. A repeated
 * change event with the same value cannot bounce a row back into the list.
 * Shift+check still extends the range from the anchor.
 */
export function applyFileListCheckbox(options: {
  visiblePaths: string[];
  selected: string[];
  anchor: string | null;
  clicked: string;
  checked: boolean;
  shiftKey?: boolean;
}): FileListSelection {
  const { visiblePaths, selected, clicked, checked } = options;
  if (checked && options.shiftKey) {
    return applyFileListSelection({
      visiblePaths,
      selected,
      anchor: options.anchor,
      clicked,
      event: { ctrlKey: true, shiftKey: true },
    });
  }
  if (checked) {
    if (selected.includes(clicked)) return { selected, anchor: clicked };
    return { selected: [...selected, clicked], anchor: clicked };
  }
  return {
    selected: selected.filter((path) => path !== clicked),
    anchor: clicked,
  };
}

/** Keep Convert/Search "current file" pointed at a still-selected row, or the library. */
export function explorerSelectionAfterFileList(options: {
  selectedVera: string[];
  selectedPdf: string[];
  clickedPath: string;
  clickedType: 'vera' | 'pdf';
  activeLibraryPath: string;
}): ExplorerSelection | null {
  const { selectedVera, selectedPdf, clickedPath, clickedType, activeLibraryPath } = options;
  if (selectedVera.includes(clickedPath) || selectedPdf.includes(clickedPath)) {
    return { kind: 'file', path: clickedPath, type: clickedType };
  }
  const remainingVera = selectedVera[selectedVera.length - 1];
  if (remainingVera) return { kind: 'file', path: remainingVera, type: 'vera' };
  const remainingPdf = selectedPdf[selectedPdf.length - 1];
  if (remainingPdf) return { kind: 'file', path: remainingPdf, type: 'pdf' };
  const folder = activeLibraryPath.trim();
  return folder ? { kind: 'folder', path: folder } : null;
}

export type ExplorerRowTone = 'selected' | 'scoped' | 'preview' | 'idle';

/** List selection, then scoped single-file search, then a quieter preview marker. */
export function explorerRowTone(options: {
  selected: boolean;
  previewing: boolean;
  scopedDocument: boolean;
}): ExplorerRowTone {
  if (options.selected) return 'selected';
  if (options.scopedDocument) return 'scoped';
  if (options.previewing) return 'preview';
  return 'idle';
}

const EXPLORER_INTERACTIVE_CLOSEST = '.fileRowWrap, .folderGroupHead, .folderEmpty, .explorerFileFilter';

type PointerNode = {
  classList: { contains(token: string): boolean };
  closest(selector: string): unknown;
};

function isPointerNode(value: unknown): value is PointerNode {
  return Boolean(
    value
    && typeof value === 'object'
    && 'classList' in value
    && 'closest' in value
    && typeof (value as PointerNode).closest === 'function',
  );
}

/**
 * Empty Explorer chrome — pane padding or leftover tree space — not file rows,
 * folder headers, or the 1px gaps inside a folder group.
 */
export function isExplorerBlankPointerTarget(
  target: unknown,
  currentTarget: unknown,
): boolean {
  if (!isPointerNode(target)) return false;
  if (target.closest(EXPLORER_INTERACTIVE_CLOSEST)) return false;
  return target === currentTarget || target.classList.contains('explorerTree');
}
