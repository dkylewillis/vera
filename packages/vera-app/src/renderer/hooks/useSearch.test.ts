import { afterEach, describe, expect, it, vi } from 'vitest';
import { SIDECAR_ACTIONS } from '../../shared/protocol';
import { createSearchController, type SearchHost } from './useSearch';

function host(overrides: Partial<SearchHost> = {}): SearchHost {
  return {
    hasSearchableScope: true,
    searchScopePath: 'C:\\lib',
    selectedFiles: [],
    activeLibraryPath: 'C:\\lib',
    searchQuery: 'detention',
    mode: 'hybrid',
    topK: 8,
    contextChunks: 0,
    includeFigures: true,
    path: 'C:\\lib',
    sourceDocument: null,
    sourceDocumentPath: '',
    results: [],
    call: async () => null,
    cancelActionScope: () => undefined,
    promptForIndexBeforeQuery: async () => false,
    loadSourceDocument: async () => undefined,
    nextSourceLoadId: () => 1,
    setErrorMessage: () => undefined,
    setSubmittedSearchQuery: () => undefined,
    setResults: () => undefined,
    setSelected: () => undefined,
    setCenterView: () => undefined,
    setCitationJumpVersion: () => undefined,
    setViewerMode: () => undefined,
    setPendingSourcePath: () => undefined,
    ...overrides,
  };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('createSearchController', () => {
  it('blocks search when the library has no VERA documents', async () => {
    const setErrorMessage = vi.fn();
    const call = vi.fn();
    const controller = createSearchController(() => host({
      hasSearchableScope: false,
      setErrorMessage,
      call,
    }));

    await controller.searchTarget();

    expect(setErrorMessage).toHaveBeenCalledWith('This library does not contain any VERA documents yet.');
    expect(call).not.toHaveBeenCalled();
  });

  it('sends a hybrid search payload and selects the first hit', async () => {
    const first = {
      chunk_id: 'chunk-1',
      score: 1,
      text: 'hit',
      page_start: 1,
      page_end: 1,
      heading_path: null,
      source_filename: 'manual.pdf',
      document_id: 'document-1',
      file: 'C:\\lib\\manual.vera',
    };
    const call = vi.fn(async () => [first]) as SearchHost['call'];
    const setResults = vi.fn();
    const setSelected = vi.fn();
    const setCenterView = vi.fn();
    const loadSourceDocument = vi.fn(async () => undefined);
    const controller = createSearchController(() => host({
      call,
      setResults,
      setSelected,
      setCenterView,
      loadSourceDocument,
      setSubmittedSearchQuery: vi.fn(),
    }));

    await controller.searchTarget();

    expect(call).toHaveBeenCalledWith(
      expect.objectContaining({
        action: SIDECAR_ACTIONS.search,
        path: 'C:\\lib',
        query: 'detention',
        mode: 'hybrid',
        include_figure_data: false,
      }),
      'Searching',
    );
    expect(setResults).toHaveBeenCalledWith([first]);
    expect(setSelected).toHaveBeenCalledWith(first);
    expect(setCenterView).toHaveBeenCalledWith('search');
    expect(loadSourceDocument).toHaveBeenCalledWith('C:\\lib\\manual.vera', false, 1);
  });
});
