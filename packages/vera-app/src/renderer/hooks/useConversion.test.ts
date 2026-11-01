import { afterEach, describe, expect, it, vi } from 'vitest';
import { createConversionController, pipelineForRun, type ConversionHost } from './useConversion';
import type { BatchConvertResult, LibrarySyncReport, StreamEvent } from '../types';

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
    libraryPaths: [],
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

  it('syncs a managed library from the Convert view instead of batch converting', async () => {
    const request = vi.fn();
    const syncLibrary = vi.fn(async () => ({ managed: true, ok: true, converted: 1, errors: [] }));
    vi.stubGlobal('window', { vera: { request, syncLibrary, onAnswerEvent: () => () => undefined } });
    const call = vi.fn() as unknown as ConversionHost['call'];
    const controller = createConversionController(() => host({ convertMode: 'batch', call }));

    const outcome = await controller.batchConvertPdfs({ directory: 'C:\\Users\\me\\Desktop\\Manuals' });

    expect(outcome).toBe('ok');
    expect(syncLibrary).toHaveBeenCalledWith('C:\\Users\\me\\Desktop\\Manuals', expect.any(String));
    expect(call).not.toHaveBeenCalled();
    expect(request).not.toHaveBeenCalled();
  });

  it('blocks convert when embedder preflight fails', async () => {
    vi.stubGlobal('window', {
      vera: { syncLibrary: async () => ({ managed: false }), onAnswerEvent: () => () => undefined },
    });
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
    expect(dispatchBackgroundTask).not.toHaveBeenCalledWith(expect.objectContaining({
      type: 'start',
      task: expect.objectContaining({ label: 'Conversion' }),
    }));
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

  describe('pipelineForRun', () => {
    const descriptor = (spec: string, formats: string[]) => ({
      provider: spec,
      variant: '',
      spec,
      label: spec,
      description: '',
      installed: true,
      capabilities: { source_formats: formats },
      fields: [{ key: 'chunk_size', label: 'Chunk size', type: 'integer' as const, default: 500 }],
    });
    const markdownSelected = {
      ingestPipeline: 'markdown',
      pipelineOptions: { max_words: 300 },
      ingestPipelineDescriptors: [descriptor('pymupdf', ['pdf']), descriptor('markdown', ['md', 'markdown'])],
      ingestPipelineConfigs: { pymupdf: { chunk_size: 800 } },
    };

    it('falls back to a PDF pipeline and its own options when PDFs are converted', () => {
      expect(pipelineForRun(markdownSelected, true)).toEqual({
        ingestPipeline: 'pymupdf',
        pipelineOptions: { chunk_size: 800 },
      });
    });

    it('keeps the selected pipeline for Markdown-only runs and PDF pipelines', () => {
      expect(pipelineForRun(markdownSelected, false)).toEqual({
        ingestPipeline: 'markdown',
        pipelineOptions: { max_words: 300 },
      });
      expect(pipelineForRun({ ...markdownSelected, ingestPipeline: 'pymupdf' }, true).ingestPipeline)
        .toBe('pymupdf');
    });
  });

  describe('quickConvert', () => {
    const library = {
      path: 'C:\\library',
      name: 'library',
      entries: [
        { path: 'C:\\library\\old.vera', name: 'old.vera', relativePath: 'old.vera', type: 'vera' as const },
        { path: 'C:\\library\\new\\report.pdf', name: 'report.pdf', relativePath: 'new/report.pdf', type: 'pdf' as const },
      ],
    };

    function batchResult(overrides: Partial<BatchConvertResult> = {}): BatchConvertResult {
      return {
        directory: 'C:\\library\\new',
        recursive: true,
        overwrite: false,
        discovered: 1,
        converted: 1,
        skipped: 0,
        user_skipped: 0,
        malformed: 0,
        failed: 0,
        outputs: [],
        skipped_existing: [],
        skipped_by_user: [],
        malformed_existing: [],
        errors: [],
        ...overrides,
      };
    }

    function setup(result: BatchConvertResult, syncReport: LibrarySyncReport | null = { managed: false }) {
      const request = vi.fn(async (payload: Record<string, unknown>) => {
        if (payload.action === 'inspect') {
          return { ok: true, result: { default_embedding_model: 'vera-hashing-384' } };
        }
        return { ok: true, result };
      });
      let progressListener: ((event: StreamEvent) => void) | null = null;
      const syncLibrary = vi.fn(async () => {
        progressListener?.({ id: 'req-quick', event: 'library_progress', phase: 'convert', completed: 0, total: 1, input: 'new/report.pdf' });
        return syncReport;
      });
      vi.stubGlobal('crypto', { randomUUID: () => 'req-quick' });
      vi.stubGlobal('window', {
        vera: {
          request,
          syncLibrary,
          onAnswerEvent: (listener: (event: StreamEvent) => void) => {
            progressListener = listener;
            return () => { progressListener = null; };
          },
        },
      });
      const setSideView = vi.fn();
      const setConversionError = vi.fn();
      const dispatchBackgroundTask = vi.fn();
      const controller = createConversionController(() => host({
        folders: [library],
        libraryPaths: ['C:\\library'],
        embeddingModel: 'sentence-transformers:all-MiniLM-L6-v2',
        batchOverwrite: true,
        call: (async () => ({ ok: true })) as ConversionHost['call'],
        setSideView,
        setConversionError,
        dispatchBackgroundTask,
      }));
      return { request, syncLibrary, setSideView, setConversionError, dispatchBackgroundTask, controller };
    }

    it('syncs a managed library instead of writing archives beside its sources', async () => {
      const { request, syncLibrary, setSideView, controller } = setup(
        batchResult(),
        { managed: true, ok: true, converted: 1, errors: [] },
      );

      await controller.quickConvert({ directory: 'C:\\library\\new' });

      expect(syncLibrary).toHaveBeenCalledWith('C:\\library\\new', 'req-quick');
      expect(request).not.toHaveBeenCalled();
      expect(setSideView).not.toHaveBeenCalled();
    });

    it('syncs the folder holding selected files, whatever kind of root Explorer shows', async () => {
      const { syncLibrary, request, controller } = setup(
        batchResult(),
        { managed: true, ok: true, converted: 1, errors: [] },
      );

      await controller.quickConvert({ paths: ['F:\\Manuals\\Chapter_66___SIGNS.docx'] });

      expect(syncLibrary).toHaveBeenCalledWith('F:\\Manuals', 'req-quick');
      expect(request).not.toHaveBeenCalled();
    });

    it('reports progress while the library syncs', async () => {
      const { dispatchBackgroundTask, controller } = setup(
        batchResult(),
        { managed: true, ok: true, converted: 1, errors: [] },
      );

      await controller.quickConvert({ directory: 'C:\\library\\new' });

      expect(dispatchBackgroundTask).toHaveBeenCalledWith(expect.objectContaining({
        type: 'start',
        task: expect.objectContaining({ kind: 'conversion', label: 'Converting new files' }),
      }));
      expect(dispatchBackgroundTask).toHaveBeenCalledWith({
        type: 'update',
        id: 'req-quick',
        update: expect.objectContaining({ message: 'Converting 1 of 1', currentItem: 'new/report.pdf' }),
      });
      expect(dispatchBackgroundTask).toHaveBeenLastCalledWith({ type: 'finish', id: 'req-quick' });
    });

    it('opens the Convert view when a library sync cannot convert a file', async () => {
      const { setSideView, setConversionError, controller } = setup(
        batchResult(),
        { managed: true, ok: false, failed: 1, errors: [{ input: 'new/report.pdf', error: 'broken' }] },
      );

      await controller.quickConvert({ directory: 'C:\\library\\new' });

      expect(setConversionError).toHaveBeenLastCalledWith('Some files did not convert:\nnew/report.pdf: broken');
      expect(setSideView).toHaveBeenCalledWith('convert');
    });

    it('converts a folder now with the library model, skipping existing archives', async () => {
      const { request, setSideView, controller } = setup(batchResult());

      await controller.quickConvert({ directory: 'C:\\library\\new' });

      expect(request).toHaveBeenCalledWith({ action: 'inspect', path: 'C:\\library\\old.vera' });
      expect(request).toHaveBeenCalledWith(
        expect.objectContaining({
          action: 'batch_convert',
          directory: 'C:\\library\\new',
          recursive: true,
          overwrite: false,
          model: 'vera-hashing-384',
        }),
        'req-quick',
      );
      expect(setSideView).not.toHaveBeenCalled();
    });

    it('opens the Convert view when a file converts with issues', async () => {
      const { setSideView, controller } = setup(batchResult({
        converted: 1,
        warnings: [{
          input: 'C:\\library\\new\\zones.docx',
          output: 'C:\\library\\new\\zones.docx.vera',
          warnings: ['Header and footer text was left out of search.'],
        }],
      }));

      await controller.quickConvert({ paths: ['C:\\library\\new\\zones.docx'] });

      expect(setSideView).toHaveBeenCalledWith('convert');
    });

    it('opens the Convert view when a file fails', async () => {
      const { setSideView, controller } = setup(batchResult({ converted: 0, failed: 1 }));

      await controller.quickConvert({ paths: ['C:\\library\\new\\report.pdf'] });

      expect(setSideView).toHaveBeenCalledWith('convert');
    });
  });
});
