import { afterEach, describe, expect, it, vi } from 'vitest';
import { createConversionController, type ConversionHost } from './useConversion';

function host(overrides: Partial<ConversionHost> = {}): ConversionHost {
  return {
    convertMode: 'selected',
    selectedPdfs: [],
    batchDirectory: '',
    batchRecursive: true,
    batchOverwrite: false,
    storeOriginal: true,
    embeddingModel: 'hashing',
    ingestPipeline: 'pymupdf',
    pipelineOptions: {},
    embedderOptions: {},
    explorerSelection: null,
    activeLibraryPath: '',
    conversionInProgress: false,
    folders: [],
    ingestPipelineDescriptors: [],
    ingestPipelineConfigs: {},
    call: async () => null,
    dispatchBackgroundTask: () => undefined,
    refreshFolder: async () => undefined,
    setBatchDirectory: () => undefined,
    setBatchOverwrite: () => undefined,
    setStoreOriginal: () => undefined,
    setConvertMode: () => undefined,
    setSideView: () => undefined,
    setSidebarCollapsed: () => undefined,
    setReconvertNotice: () => undefined,
    setReconvertBusy: () => undefined,
    setConversionError: () => undefined,
    setBatchConvertResult: () => undefined,
    setSelectedPdfs: () => undefined,
    setExplorerSelection: () => undefined,
    setEmbeddingModel: () => undefined,
    setIngestPipeline: () => undefined,
    setIngestPipelineConfigs: () => undefined,
    setPipelineOptions: () => undefined,
    ...overrides,
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('createConversionController', () => {
  it('does not start a convert when no PDFs or directory are chosen', async () => {
    const setConversionError = vi.fn();
    const dispatchBackgroundTask = vi.fn();
    const controller = createConversionController(() => host({
      convertMode: 'selected',
      setConversionError,
      dispatchBackgroundTask,
    }));

    await controller.batchConvertPdfs({ paths: [] });

    expect(setConversionError).toHaveBeenCalledWith(
      'Select one or more PDFs or Markdown files in Explorer (click, Ctrl/Cmd+click, or Shift+click).',
    );
    expect(dispatchBackgroundTask).not.toHaveBeenCalled();
  });

  it('opens convert for a folder in batch mode', () => {
    const setConvertMode = vi.fn();
    const setSideView = vi.fn();
    const setBatchDirectory = vi.fn();
    const controller = createConversionController(() => host({
      setConvertMode,
      setSideView,
      setBatchDirectory,
      setExplorerSelection: vi.fn(),
      setReconvertNotice: vi.fn(),
      setConversionError: vi.fn(),
      setSidebarCollapsed: vi.fn(),
    }));

    controller.openConvertFolder('C:\\library');

    expect(setBatchDirectory).toHaveBeenCalledWith('C:\\library');
    expect(setConvertMode).toHaveBeenCalledWith('batch');
    expect(setSideView).toHaveBeenCalledWith('convert');
  });

  it('blocks convert when embedder preflight fails', async () => {
    const setConversionError = vi.fn();
    const dispatchBackgroundTask = vi.fn();
    const call = vi.fn(async () => ({
      ok: false,
      missing_credential_env: 'OPENAI_API_KEY',
      detail: 'missing key',
    })) as ConversionHost['call'];
    const controller = createConversionController(() => host({
      convertMode: 'selected',
      embeddingModel: 'openai:text-embedding-3-small',
      call,
      setConversionError,
      dispatchBackgroundTask,
    }));

    await controller.batchConvertPdfs({ paths: ['C:\\docs\\a.pdf'] });

    expect(call).toHaveBeenCalledWith(
      expect.objectContaining({ action: 'preflight_embedder', model: 'openai:text-embedding-3-small' }),
      'Checking embedder',
    );
    expect(setConversionError).toHaveBeenCalledWith(
      'Embedding provider is not ready. Set OPENAI_API_KEY under File > Settings → Embeddings, then convert again.',
    );
    expect(dispatchBackgroundTask).not.toHaveBeenCalled();
  });

  it('does not prefill a Docling pipeline the desktop Convert view cannot run', async () => {
    const setIngestPipeline = vi.fn();
    const setConversionError = vi.fn();
    const setIngestPipelineConfigs = vi.fn();
    const call = vi.fn(async () => ({
      parser_name: 'docling',
      default_embedding_model: 'hashing',
      source_file_name: 'manual.pdf',
      source_attachment_id: 'source_original',
    })) as ConversionHost['call'];
    const controller = createConversionController(() => host({
      ingestPipeline: 'pymupdf',
      ingestPipelineDescriptors: [{
        provider: 'pymupdf',
        variant: '',
        spec: 'pymupdf',
        label: 'PyMuPDF',
        description: 'Default PDF pipeline',
        installed: true,
        capabilities: { overlap_supported: true },
        fields: [],
      }],
      folders: [{
        path: 'C:\\library',
        name: 'library',
        entries: [
          {
            path: 'C:\\library\\manual.vera',
            name: 'manual.vera',
            relativePath: 'manual.vera',
            type: 'vera',
          },
          {
            path: 'C:\\library\\manual.pdf',
            name: 'manual.pdf',
            relativePath: 'manual.pdf',
            type: 'pdf',
          },
        ],
      }],
      call,
      setIngestPipeline,
      setConversionError,
      setEmbeddingModel: vi.fn(),
      setIngestPipelineConfigs,
      setPipelineOptions: vi.fn(),
      setSelectedPdfs: vi.fn(),
      setExplorerSelection: vi.fn(),
      setReconvertNotice: vi.fn(),
      setReconvertBusy: vi.fn(),
      setStoreOriginal: vi.fn(),
      setBatchOverwrite: vi.fn(),
      setConvertMode: vi.fn(),
      setSideView: vi.fn(),
      setSidebarCollapsed: vi.fn(),
    }));

    await controller.openReconvert(
      {
        path: 'C:\\library\\manual.vera',
        name: 'manual.vera',
        relativePath: 'manual.vera',
        type: 'vera',
      },
      'C:\\library',
    );

    expect(setConversionError.mock.calls.every(([value]) => value == null)).toBe(true);
    expect(setIngestPipeline).not.toHaveBeenCalled();
    expect(setIngestPipelineConfigs).toHaveBeenCalled();
    const updater = setIngestPipelineConfigs.mock.calls[0][0] as (
      prev: Record<string, unknown>,
    ) => Record<string, unknown>;
    expect(Object.keys(updater({}))).toEqual(['pymupdf']);
  });

  it('reconvert writes to the clicked archive instead of source.with_suffix(.vera)', async () => {
    const request = vi.fn(async (payload: Record<string, unknown>) => {
      if (payload.action === 'convert') {
        return { ok: true, result: { output: payload.output } };
      }
      return { ok: true, result: { converted: 0 } };
    });
    vi.stubGlobal('crypto', { randomUUID: () => 'req-reconvert' });
    vi.stubGlobal('window', {
      vera: {
        pathExists: async () => true,
        request,
        onAnswerEvent: () => () => undefined,
      },
    });
    const call = vi.fn(async (payload: Record<string, unknown>) => {
      if (payload.action === 'inspect') {
        return {
          source_file_name: 'report.pdf',
          source_attachment_id: 'source_original',
          parser_name: 'pymupdf',
          default_embedding_model: 'hashing',
        };
      }
      if (payload.action === 'preflight_embedder') return { ok: true };
      return null;
    }) as ConversionHost['call'];
    const setBatchConvertResult = vi.fn();
    const setSelectedPdfs = vi.fn();
    const controller = createConversionController(() => host({
      call,
      folders: [{
        path: 'C:\\library',
        name: 'library',
        entries: [
          {
            path: 'C:\\library\\project-alpha.vera',
            name: 'project-alpha.vera',
            relativePath: 'project-alpha.vera',
            type: 'vera',
          },
          {
            path: 'C:\\library\\report.pdf',
            name: 'report.pdf',
            relativePath: 'report.pdf',
            type: 'pdf',
          },
        ],
      }],
      selectedPdfs: ['C:\\library\\report.pdf'],
      embeddingModel: 'hashing',
      ingestPipeline: 'pymupdf',
      batchOverwrite: true,
      storeOriginal: true,
      ingestPipelineDescriptors: [{
        provider: 'pymupdf',
        variant: '',
        spec: 'pymupdf',
        label: 'PyMuPDF',
        description: '',
        installed: true,
        capabilities: { source_formats: ['pdf'] },
        fields: [],
      }],
      setSelectedPdfs,
      setBatchConvertResult,
      dispatchBackgroundTask: vi.fn(),
      setReconvertNotice: vi.fn(),
      setReconvertBusy: vi.fn(),
      setConversionError: vi.fn(),
      setConvertMode: vi.fn(),
      setSideView: vi.fn(),
      setSidebarCollapsed: vi.fn(),
      setEmbeddingModel: vi.fn(),
      setIngestPipeline: vi.fn(),
      setIngestPipelineConfigs: vi.fn(),
      setPipelineOptions: vi.fn(),
      setStoreOriginal: vi.fn(),
      setBatchOverwrite: vi.fn(),
      setExplorerSelection: vi.fn(),
      refreshFolder: async () => undefined,
    }));

    await controller.openReconvert(
      {
        path: 'C:\\library\\project-alpha.vera',
        name: 'project-alpha.vera',
        relativePath: 'project-alpha.vera',
        type: 'vera',
      },
      'C:\\library',
    );
    await controller.batchConvertPdfs({ paths: ['C:\\library\\report.pdf'] });

    expect(request).toHaveBeenCalledWith(
      expect.objectContaining({
        action: 'convert',
        input: 'C:\\library\\report.pdf',
        output: 'C:\\library\\project-alpha.vera',
      }),
      'req-reconvert',
    );
    expect(request).not.toHaveBeenCalledWith(
      expect.objectContaining({ action: 'batch_convert' }),
      expect.anything(),
    );
    expect(setBatchConvertResult).toHaveBeenCalledWith(
      expect.objectContaining({
        converted: 1,
        outputs: ['C:\\library\\project-alpha.vera'],
      }),
    );
  });
});
