import { describe, expect, it, vi } from 'vitest';
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
});
