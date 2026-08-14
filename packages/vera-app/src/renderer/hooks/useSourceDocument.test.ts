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
});
