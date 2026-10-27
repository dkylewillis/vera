import { describe, expect, it, vi } from 'vitest';
import {
  applyFileListCheckbox,
  applyFileListSelection,
  explorerEntryType,
  explorerFileMatchesFilter,
  explorerRowTone,
  explorerSelectionAfterFileList,
  isDirectoryOpenTarget,
  isExplorerBlankPointerTarget,
  partitionExplorerSelection,
  pruneExplorerSelectionForFilter,
  buildExplorerTree,
  filterExplorerTree,
  pairExplorerDocuments,
  pendingSourcesInTree,
  routeOpenTarget,
  syncCollapsedFolders,
  visibleExplorerDocuments,
} from './explorer';

describe('syncCollapsedFolders', () => {
  it('keeps the current expansion when no library is active', () => {
    expect(syncCollapsedFolders(['/a', '/b'], '', ['/b'])).toEqual(['/b']);
  });

  it('drops closed folders from the collapsed list when none is active', () => {
    expect(syncCollapsedFolders(['/a'], '', ['/a', '/gone'])).toEqual(['/a']);
  });

  it('expands every remaining folder when none is active and none were collapsed', () => {
    expect(syncCollapsedFolders(['/a', '/b'], '')).toEqual([]);
  });

  it('keeps the active library expanded and collapses the rest', () => {
    expect(syncCollapsedFolders(['/a', '/b', '/c'], '/b', ['/a'])).toEqual(['/a', '/c']);
  });

  it('expands a lone active library', () => {
    expect(syncCollapsedFolders(['/only'], '/only', ['/only'])).toEqual([]);
  });

  it('seeds startup collapse from saved folders and the last active library', () => {
    expect(syncCollapsedFolders(['/a', '/b', '/c'], '/a')).toEqual(['/b', '/c']);
  });

  it('leaves plain folders in their current state when a library activates', () => {
    expect(syncCollapsedFolders(['/lib', '/other', '/plain', '/closed'], '/lib', ['/closed'], ['/lib', '/other']))
      .toEqual(['/other', '/closed']);
  });
});

describe('partitionExplorerSelection', () => {
  it('splits mixed paths by extension', () => {
    expect(partitionExplorerSelection(['a.vera', 'b.pdf', 'c.VERA', 'notes.txt', 'guide.md'])).toEqual({
      vera: ['a.vera', 'c.VERA'],
      pdf: ['b.pdf'],
      md: ['guide.md'],
    });
  });
});

describe('explorerEntryType', () => {
  it('recognizes archive, PDF, and Markdown extensions', () => {
    expect(explorerEntryType('manual.vera')).toBe('vera');
    expect(explorerEntryType('manual.PDF')).toBe('pdf');
    expect(explorerEntryType('readme.md')).toBe('md');
    expect(explorerEntryType('notes.markdown')).toBe('md');
    expect(explorerEntryType('notes.txt')).toBeNull();
  });
});

function entry(root: string, relativePath: string) {
  const name = relativePath.split('/').pop() as string;
  return {
    path: `${root}/${relativePath}`,
    name,
    relativePath,
    type: explorerEntryType(name) as 'vera' | 'pdf' | 'md',
  };
}

describe('pairExplorerDocuments', () => {
  it('shows a source and its archive as one ready document', () => {
    const docs = pairExplorerDocuments([
      entry('/lib', 'budget.pdf'),
      entry('/lib', 'budget.vera'),
      entry('/lib', 'notes.md'),
      entry('/lib', 'orphan.vera'),
    ]);
    expect(docs.map((doc) => [doc.label, doc.path, doc.type, Boolean(doc.source)])).toEqual([
      ['budget', '/lib/budget.vera', 'vera', true],
      ['notes.md', '/lib/notes.md', 'md', true],
      ['orphan', '/lib/orphan.vera', 'vera', false],
    ]);
  });

  it('pairs the PDF when a PDF and Markdown file share a stem', () => {
    const docs = pairExplorerDocuments([
      entry('/lib', 'a.md'),
      entry('/lib', 'a.pdf'),
      entry('/lib', 'a.vera'),
    ]);
    expect(docs.map((doc) => [doc.label, doc.source?.name])).toEqual([
      ['a', 'a.pdf'],
      ['a.md', 'a.md'],
    ]);
  });
});

describe('buildExplorerTree', () => {
  const root = {
    path: 'C:\\lib',
    name: 'lib',
    entries: [
      entry('C:\\lib', 'top.vera'),
      entry('C:\\lib', 'reports/2024/q1.pdf'),
      entry('C:\\lib', 'reports/2024/q1.vera'),
      entry('C:\\lib', 'reports/2024/q2.pdf'),
      entry('C:\\lib', 'specs/a.vera'),
      entry('C:\\lib', 'specs/drafts/b.md'),
    ],
  };

  it('nests subfolders, compacts single-child chains, and counts the subtree', () => {
    const tree = buildExplorerTree(root);
    expect(tree.path).toBe('C:\\lib');
    expect(tree.documents.map((doc) => doc.label)).toEqual(['top']);
    expect(tree.folders.map((folder) => [folder.name, folder.path])).toEqual([
      ['reports/2024', 'C:\\lib\\reports\\2024'],
      ['specs', 'C:\\lib\\specs'],
    ]);
    expect(tree.folders[1].folders.map((folder) => folder.name)).toEqual(['drafts']);
    expect([tree.readyCount, tree.pendingCount]).toEqual([3, 2]);
    expect([tree.folders[0].readyCount, tree.folders[0].pendingCount]).toEqual([1, 1]);
    expect(pendingSourcesInTree(tree)).toEqual([
      'C:\\lib/reports/2024/q2.pdf',
      'C:\\lib/specs/drafts/b.md',
    ]);
  });

  it('filters documents and drops subfolders left empty', () => {
    const pending = filterExplorerTree(buildExplorerTree(root), 'pending');
    expect(pending.documents).toEqual([]);
    expect(pending.folders.map((folder) => folder.name)).toEqual(['reports/2024', 'specs']);
    expect(pending.folders[1].documents).toEqual([]);
    const ready = filterExplorerTree(buildExplorerTree(root), 'ready');
    expect(ready.folders[1].folders).toEqual([]);
  });

  it('lists visible rows in tree order, skipping collapsed roots and subfolders', () => {
    const tree = buildExplorerTree(root);
    expect(visibleExplorerDocuments([tree], [], []).map((doc) => doc.label)).toEqual(['top']);
    expect(visibleExplorerDocuments([tree], [], ['C:\\lib\\reports\\2024']).map((doc) => doc.label))
      .toEqual(['q1', 'q2.pdf', 'top']);
    expect(visibleExplorerDocuments([tree], ['C:\\lib'], ['C:\\lib\\reports\\2024'])).toEqual([]);
  });
});

describe('routeOpenTarget', () => {
  it('treats folders as directory targets and archives as files', () => {
    expect(isDirectoryOpenTarget('C:\\library')).toBe(true);
    expect(isDirectoryOpenTarget('C:\\library\\manual.vera')).toBe(false);
    expect(isDirectoryOpenTarget('')).toBe(false);
  });

  it('routes File → Open Folder through add-folder and archives through open-file', () => {
    const addFolder = vi.fn();
    const openFile = vi.fn();
    routeOpenTarget('C:\\proposals', { addFolder, openFile }, 'folder');
    routeOpenTarget('C:\\proposals\\manual.vera', { addFolder, openFile });
    expect(addFolder).toHaveBeenCalledWith('C:\\proposals', 'folder');
    expect(openFile).toHaveBeenCalledWith('C:\\proposals\\manual.vera');
  });

  it('opens directories without a kind as libraries', () => {
    const addFolder = vi.fn();
    routeOpenTarget('C:\\proposals', { addFolder, openFile: vi.fn() });
    expect(addFolder).toHaveBeenCalledWith('C:\\proposals', 'library');
  });
});

describe('pruneExplorerSelectionForFilter', () => {
  const mixed = ['/lib/a.vera', '/lib/b.pdf', '/lib/c.vera'];

  it('keeps the full selection for All', () => {
    expect(pruneExplorerSelectionForFilter(mixed, 'all', '/lib/b.pdf')).toEqual({
      selected: mixed,
      anchor: '/lib/b.pdf',
    });
  });

  it('drops unconverted sources when filtering to Ready', () => {
    expect(pruneExplorerSelectionForFilter(mixed, 'ready', '/lib/b.pdf')).toEqual({
      selected: ['/lib/a.vera', '/lib/c.vera'],
      anchor: null,
    });
  });

  it('drops archives when filtering to To convert and keeps a still-visible anchor', () => {
    expect(pruneExplorerSelectionForFilter(mixed, 'pending', '/lib/b.pdf')).toEqual({
      selected: ['/lib/b.pdf'],
      anchor: '/lib/b.pdf',
    });
  });

  it('reports whether a row type remains visible under the filter', () => {
    expect(explorerFileMatchesFilter('pdf', 'ready')).toBe(false);
    expect(explorerFileMatchesFilter('md', 'pending')).toBe(true);
    expect(explorerFileMatchesFilter('pdf', 'all')).toBe(true);
    expect(explorerFileMatchesFilter('vera', 'ready')).toBe(true);
  });
});

describe('applyFileListSelection', () => {
  const visible = ['a.vera', 'b.vera', 'c.vera', 'd.pdf'];

  it('replaces the selection on a plain click', () => {
    expect(applyFileListSelection({
      visiblePaths: visible,
      selected: ['a.vera', 'c.vera'],
      anchor: 'c.vera',
      clicked: 'b.vera',
      event: {},
    })).toEqual({ selected: ['b.vera'], anchor: 'b.vera' });
  });

  it('toggles membership with Ctrl/Cmd+click', () => {
    expect(applyFileListSelection({
      visiblePaths: visible,
      selected: ['a.vera'],
      anchor: 'a.vera',
      clicked: 'c.vera',
      event: { ctrlKey: true },
    })).toEqual({ selected: ['a.vera', 'c.vera'], anchor: 'c.vera' });

    expect(applyFileListSelection({
      visiblePaths: visible,
      selected: ['a.vera', 'c.vera'],
      anchor: 'c.vera',
      clicked: 'a.vera',
      event: { metaKey: true },
    })).toEqual({ selected: ['c.vera'], anchor: 'a.vera' });
  });

  it('can deselect the last selected file with Ctrl/Cmd+click', () => {
    expect(applyFileListSelection({
      visiblePaths: visible,
      selected: ['b.vera'],
      anchor: 'b.vera',
      clicked: 'b.vera',
      event: { ctrlKey: true },
    })).toEqual({ selected: [], anchor: 'b.vera' });
  });

  it('selects an inclusive range with Shift+click', () => {
    expect(applyFileListSelection({
      visiblePaths: visible,
      selected: ['a.vera'],
      anchor: 'a.vera',
      clicked: 'c.vera',
      event: { shiftKey: true },
    })).toEqual({ selected: ['a.vera', 'b.vera', 'c.vera'], anchor: 'a.vera' });
  });

  it('selects a range in either direction without moving the anchor', () => {
    expect(applyFileListSelection({
      visiblePaths: visible,
      selected: ['c.vera'],
      anchor: 'c.vera',
      clicked: 'a.vera',
      event: { shiftKey: true },
    })).toEqual({ selected: ['a.vera', 'b.vera', 'c.vera'], anchor: 'c.vera' });
  });

  it('adds a range with Ctrl+Shift+click', () => {
    expect(applyFileListSelection({
      visiblePaths: visible,
      selected: ['d.pdf'],
      anchor: 'd.pdf',
      clicked: 'b.vera',
      event: { ctrlKey: true, shiftKey: true },
    })).toEqual({ selected: ['d.pdf', 'b.vera', 'c.vera'], anchor: 'd.pdf' });
  });

  it('treats Shift+click without a visible anchor as a plain click', () => {
    expect(applyFileListSelection({
      visiblePaths: visible,
      selected: ['a.vera'],
      anchor: '/missing.vera',
      clicked: 'c.vera',
      event: { shiftKey: true },
    })).toEqual({ selected: ['c.vera'], anchor: 'c.vera' });
  });
});

describe('applyFileListCheckbox', () => {
  const visible = ['a.vera', 'b.vera', 'c.vera', 'd.pdf'];

  it('unchecks a row without toggling it back on', () => {
    expect(applyFileListCheckbox({
      visiblePaths: visible,
      selected: ['a.vera', 'b.vera'],
      anchor: 'a.vera',
      clicked: 'b.vera',
      checked: false,
    })).toEqual({ selected: ['a.vera'], anchor: 'b.vera' });
  });

  it('unchecking the only selected file leaves an empty list', () => {
    expect(applyFileListCheckbox({
      visiblePaths: visible,
      selected: ['a.vera'],
      anchor: 'a.vera',
      clicked: 'a.vera',
      checked: false,
    })).toEqual({ selected: [], anchor: 'a.vera' });
  });

  it('is idempotent when the native change event repeats', () => {
    const once = applyFileListCheckbox({
      visiblePaths: visible,
      selected: ['a.vera'],
      anchor: 'a.vera',
      clicked: 'a.vera',
      checked: false,
    });
    expect(applyFileListCheckbox({
      visiblePaths: visible,
      selected: once.selected,
      anchor: once.anchor,
      clicked: 'a.vera',
      checked: false,
    })).toEqual({ selected: [], anchor: 'a.vera' });
  });

  it('checks a row onto the current selection', () => {
    expect(applyFileListCheckbox({
      visiblePaths: visible,
      selected: ['a.vera'],
      anchor: 'a.vera',
      clicked: 'c.vera',
      checked: true,
    })).toEqual({ selected: ['a.vera', 'c.vera'], anchor: 'c.vera' });
  });

  it('extends the range when Shift+checking', () => {
    expect(applyFileListCheckbox({
      visiblePaths: visible,
      selected: ['a.vera'],
      anchor: 'a.vera',
      clicked: 'c.vera',
      checked: true,
      shiftKey: true,
    })).toEqual({ selected: ['a.vera', 'b.vera', 'c.vera'], anchor: 'a.vera' });
  });
});

describe('explorerSelectionAfterFileList', () => {
  it('keeps the clicked file when it is still selected', () => {
    expect(explorerSelectionAfterFileList({
      selectedVera: ['a.vera', 'b.vera'],
      selectedPdf: [],
      clickedPath: 'b.vera',
      clickedType: 'vera',
      activeLibraryPath: 'C:\\lib',
    })).toEqual({ kind: 'file', path: 'b.vera', type: 'vera' });
  });

  it('falls back to a remaining file after unchecking one', () => {
    expect(explorerSelectionAfterFileList({
      selectedVera: ['a.vera'],
      selectedPdf: [],
      clickedPath: 'b.vera',
      clickedType: 'vera',
      activeLibraryPath: 'C:\\lib',
    })).toEqual({ kind: 'file', path: 'a.vera', type: 'vera' });
  });

  it('restores the active library when the list is empty', () => {
    expect(explorerSelectionAfterFileList({
      selectedVera: [],
      selectedPdf: [],
      clickedPath: 'a.vera',
      clickedType: 'vera',
      activeLibraryPath: 'C:\\lib',
    })).toEqual({ kind: 'folder', path: 'C:\\lib' });
  });
});

describe('explorerRowTone', () => {
  it('prefers list selection over preview and scoped-document fallbacks', () => {
    expect(explorerRowTone({ selected: true, previewing: true, scopedDocument: true })).toBe('selected');
  });

  it('keeps a scoped single file highlighted only when nothing is listed', () => {
    expect(explorerRowTone({ selected: false, previewing: false, scopedDocument: true })).toBe('scoped');
  });

  it('uses a quieter preview marker when the row is not selected', () => {
    expect(explorerRowTone({ selected: false, previewing: true, scopedDocument: false })).toBe('preview');
    expect(explorerRowTone({ selected: false, previewing: false, scopedDocument: false })).toBe('idle');
  });
});

describe('isExplorerBlankPointerTarget', () => {
  function fakeTarget(className: string, ancestor?: string) {
    const classes = new Set([className, ancestor].filter(Boolean) as string[]);
    return {
      classList: { contains: (token: string) => token === className },
      closest: (selector: string) => {
        const tokens = selector.split(',').map((item) => item.trim().replace(/^\./, ''));
        return tokens.some((token) => classes.has(token)) ? {} : null;
      },
    };
  }

  it('treats pane chrome and leftover tree space as a clear click', () => {
    const pane = fakeTarget('sidePanelBody');
    expect(isExplorerBlankPointerTarget(pane, pane)).toBe(true);
    expect(isExplorerBlankPointerTarget(fakeTarget('explorerTree'), pane)).toBe(true);
  });

  it('ignores file rows, folder headers, and gaps inside a folder group', () => {
    const pane = fakeTarget('sidePanelBody');
    expect(isExplorerBlankPointerTarget(fakeTarget('fileRowWrap'), pane)).toBe(false);
    expect(isExplorerBlankPointerTarget(fakeTarget('folderGroupHead'), pane)).toBe(false);
    expect(isExplorerBlankPointerTarget(fakeTarget('folderGroup'), pane)).toBe(false);
    expect(isExplorerBlankPointerTarget(null, pane)).toBe(false);
  });
});
