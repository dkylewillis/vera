/**
 * Keep Explorer scannable around the active library without fighting file
 * selection: expand the active library and collapse the rest when one is set;
 * when none is active (e.g. a single .vera is scoped), preserve the user's
 * expand/collapse state and only drop folders that are no longer open.
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
