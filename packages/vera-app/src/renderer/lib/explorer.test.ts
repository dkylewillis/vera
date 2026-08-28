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
  routeOpenTarget,
  syncCollapsedFolders,
  visibleExplorerEntries,
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

describe('visibleExplorerEntries', () => {
  const folders = [
    {
      path: '/lib',
      entries: [
        { path: '/lib/a.vera', type: 'vera' as const },
        { path: '/lib/b.pdf', type: 'pdf' as const },
      ],
    },
    {
      path: '/other',
      entries: [{ path: '/other/c.vera', type: 'vera' as const }],
    },
  ];

  it('skips collapsed folders and honors the type filter', () => {
    expect(visibleExplorerEntries(folders, ['/other'], 'vera').map((entry) => entry.path)).toEqual([
      '/lib/a.vera',
    ]);
    expect(visibleExplorerEntries(folders, [], 'all').map((entry) => entry.path)).toEqual([
      '/lib/a.vera',
      '/lib/b.pdf',
      '/other/c.vera',
    ]);
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
    routeOpenTarget('C:\\proposals', { addFolder, openFile });
    routeOpenTarget('C:\\proposals\\manual.vera', { addFolder, openFile });
    expect(addFolder).toHaveBeenCalledWith('C:\\proposals');
    expect(openFile).toHaveBeenCalledWith('C:\\proposals\\manual.vera');
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

  it('drops hidden PDFs when filtering to VERA', () => {
    expect(pruneExplorerSelectionForFilter(mixed, 'vera', '/lib/b.pdf')).toEqual({
      selected: ['/lib/a.vera', '/lib/c.vera'],
      anchor: null,
    });
  });

  it('drops hidden archives when filtering to PDFs and keeps a still-visible anchor', () => {
    expect(pruneExplorerSelectionForFilter(mixed, 'pdf', '/lib/b.pdf')).toEqual({
      selected: ['/lib/b.pdf'],
      anchor: '/lib/b.pdf',
    });
  });

  it('reports whether a file type remains visible under the filter', () => {
    expect(explorerFileMatchesFilter('pdf', 'vera')).toBe(false);
    expect(explorerFileMatchesFilter('pdf', 'all')).toBe(true);
    expect(explorerFileMatchesFilter('vera', 'vera')).toBe(true);
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
