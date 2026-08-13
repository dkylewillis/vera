import { describe, expect, it, vi } from 'vitest';
import {
  applyFileListSelection,
  explorerEntryType,
  explorerFileMatchesFilter,
  isDirectoryOpenTarget,
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
});

describe('partitionExplorerSelection', () => {
  it('splits mixed paths by extension', () => {
    expect(partitionExplorerSelection(['a.vera', 'b.pdf', 'c.VERA', 'notes.txt'])).toEqual({
      vera: ['a.vera', 'c.VERA'],
      pdf: ['b.pdf'],
    });
  });
});

describe('explorerEntryType', () => {
  it('recognizes archive and PDF extensions', () => {
    expect(explorerEntryType('manual.vera')).toBe('vera');
    expect(explorerEntryType('manual.PDF')).toBe('pdf');
    expect(explorerEntryType('readme.md')).toBeNull();
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
