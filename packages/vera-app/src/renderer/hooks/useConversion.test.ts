import { afterEach, describe, expect, it, vi } from 'vitest';
import { DOCLING_PREPARE_STOP_CONFIRM } from '../lib/conversion';
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
      'Select one or more PDFs in Explorer (click, Ctrl/Cmd+click, or Shift+click).',
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
      'Embedding provider is not ready. This build does not include hosted embedders; OPENAI_API_KEY cannot be configured here yet.',
    );
    expect(dispatchBackgroundTask).not.toHaveBeenCalled();
  });

  it('prefetches Docling models when the Advanced layout pipeline is selected', async () => {
    const dispatchBackgroundTask = vi.fn();
    const request = vi.fn(async () => ({
      ok: true,
      result: { ready: true, downloaded: false, artifacts_path: 'C:\\cache' },
    }));
    vi.stubGlobal('window', {
      vera: {
        request,
        onAnswerEvent: () => () => undefined,
        cancelAnswer: vi.fn(),
      },
    });
    const controller = createConversionController(() => host({
      ingestPipeline: 'docling',
      ingestPipelineDescriptors: [{
        provider: 'docling',
        variant: 'hybrid',
        spec: 'docling',
        label: 'Advanced layout',
        description: '',
        installed: true,
        capabilities: {},
        fields: [],
        notes: [],
        source: 'bundled',
      }],
      dispatchBackgroundTask,
    }));

    await controller.prepareDoclingModels();

    expect(request).toHaveBeenCalledWith(
      expect.objectContaining({ action: 'prepare_docling' }),
      expect.any(String),
    );
    expect(dispatchBackgroundTask).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'start',
        task: expect.objectContaining({ kind: 'docling_prepare' }),
      }),
    );
  });

  it('asks before stopping a Docling model download', async () => {
    const cancelAnswer = vi.fn(async () => ({ cancelled: true }));
    const confirm = vi.fn(() => false);
    let finish: ((value: { ok: boolean; result: { ready: boolean } }) => void) | undefined;
    const request = vi.fn(() => new Promise<{ ok: boolean; result: { ready: boolean } }>((resolve) => {
      finish = resolve;
    }));
    vi.stubGlobal('window', {
      confirm,
      vera: {
        request,
        onAnswerEvent: () => () => undefined,
        cancelAnswer,
      },
    });
    const controller = createConversionController(() => host({
      ingestPipeline: 'docling',
      ingestPipelineDescriptors: [{
        provider: 'docling',
        variant: '',
        spec: 'docling',
        label: 'Advanced layout',
        description: '',
        installed: true,
        capabilities: {},
        fields: [],
        notes: [],
        source: 'bundled',
      }],
      conversionInProgress: false,
    }));
    const pending = controller.prepareDoclingModels();
    controller.stopConversion();
    expect(confirm).toHaveBeenCalledWith(DOCLING_PREPARE_STOP_CONFIRM);
    expect(cancelAnswer).not.toHaveBeenCalled();
    finish?.({ ok: true, result: { ready: true } });
    await pending;
  });
});
