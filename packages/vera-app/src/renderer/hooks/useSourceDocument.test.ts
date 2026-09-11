import { describe, expect, it, vi } from 'vitest';
import { SIDECAR_ACTIONS } from '../../shared/protocol';
import { createSourceDocumentController, type SourceDocumentHost } from './useSourceDocument';

function host(overrides: Partial<SourceDocumentHost> = {}): SourceDocumentHost {
  return {
    path: 'C:\\lib\\manual.vera',
    folders: [],
    pendingSourcePath: '',
    sourceDocument: null,
    sourceDocumentPath: '',
    call: async () => null,
    cancelActionScope: () => undefined,
    openTargetPath: async () => undefined,
    applyConvertDefaultsFromSelection: () => undefined,
    setPendingSourcePath: () => undefined,
    setLibraryInfoPath: () => undefined,
    setSourceDocument: () => undefined,
    setSourceDocumentPath: () => undefined,
    setViewerMode: () => undefined,
    setViewerCollapsed: () => undefined,
    setExplorerSelection: () => undefined,
    setSelected: () => undefined,
    ...overrides,
  };
}

describe('createSourceDocumentController', () => {
  it('does not request source bytes for a library folder', async () => {
    const call = vi.fn();
    const setPendingSourcePath = vi.fn();
    const controller = createSourceDocumentController(() => host({
      folders: [{ path: 'C:\\lib', name: 'lib', entries: [] }],
      call,
      setPendingSourcePath,
    }));

    await controller.loadSourceDocument('C:\\lib');

    expect(call).not.toHaveBeenCalled();
    expect(setPendingSourcePath).toHaveBeenCalledWith('');
  });

  it('loads source bytes and activates the document viewer', async () => {
    const source = {
      filename: 'manual.pdf',
      mime_type: 'application/pdf',
      hash: 'abc',
      size: 12,
      url: 'vera-source://manual',
    };
    const call = vi.fn(async () => source) as SourceDocumentHost['call'];
    const setSourceDocument = vi.fn();
    const setViewerMode = vi.fn();
    const controller = createSourceDocumentController(() => host({
      call,
      setSourceDocument,
      setSourceDocumentPath: vi.fn(),
      setLibraryInfoPath: vi.fn(),
      setPendingSourcePath: vi.fn(),
      setViewerMode,
    }));

    await controller.loadSourceDocument('C:\\lib\\manual.vera');

    expect(call).toHaveBeenCalledWith(
      { action: SIDECAR_ACTIONS.source, path: 'C:\\lib\\manual.vera' },
      'Loading source',
      undefined,
      { scope: 'source' },
    );
    expect(setSourceDocument).toHaveBeenCalledWith(source);
    expect(setViewerMode).toHaveBeenCalledWith('document');
  });

  it('previews Markdown sources the same way as PDFs', async () => {
    const source = {
      filename: 'notes.md',
      mime_type: 'text/markdown',
      hash: 'def',
      size: 8,
      url: 'vera-source://notes',
    };
    const call = vi.fn(async () => source) as SourceDocumentHost['call'];
    const applyConvertDefaultsFromSelection = vi.fn();
    const setExplorerSelection = vi.fn();
    const controller = createSourceDocumentController(() => host({
      call,
      applyConvertDefaultsFromSelection,
      setExplorerSelection,
      setLibraryInfoPath: vi.fn(),
      setPendingSourcePath: vi.fn(),
      setSourceDocument: vi.fn(),
      setSourceDocumentPath: vi.fn(),
      setViewerMode: vi.fn(),
      setViewerCollapsed: vi.fn(),
      setSelected: vi.fn(),
    }));

    await controller.previewSourceDocument({
      path: 'C:\\lib\\notes.md',
      name: 'notes.md',
      relativePath: 'notes.md',
      type: 'md',
    });

    expect(applyConvertDefaultsFromSelection).toHaveBeenCalledWith({
      kind: 'file',
      path: 'C:\\lib\\notes.md',
      type: 'md',
    });
    expect(call).toHaveBeenCalledWith(
      { action: SIDECAR_ACTIONS.source, path: 'C:\\lib\\notes.md' },
      'Loading source',
      undefined,
      { scope: 'source' },
    );
  });
});
