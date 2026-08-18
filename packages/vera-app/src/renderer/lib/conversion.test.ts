import { describe, expect, it, vi } from 'vitest';
import { SIDECAR_ACTIONS } from '../../shared/protocol';
import {
  awaitConversionRequest,
  buildBatchConvertPayload,
  conversionFailedMessage,
  conversionMissingTargetMessage,
  conversionProgressTaskUpdate,
  ingestPipelineIsDocling,
  shouldConfirmDoclingPrepareStop,
  DOCLING_PREPARE_STOP_CONFIRM,
} from './conversion';

describe('awaitConversionRequest', () => {
  it('settles the active request before follow-up work starts', async () => {
    const events: string[] = [];

    const result = await awaitConversionRequest(
      Promise.resolve('converted'),
      () => events.push('request settled'),
    );
    events.push('refresh library');

    expect(result).toBe('converted');
    expect(events).toEqual(['request settled', 'refresh library']);
  });

  it('settles the active request when the sidecar rejects', async () => {
    const onSettled = vi.fn();

    await expect(
      awaitConversionRequest(Promise.reject(new Error('sidecar exited')), onSettled),
    ).rejects.toThrow('sidecar exited');

    expect(onSettled).toHaveBeenCalledOnce();
  });
});

describe('conversionProgressTaskUpdate', () => {
  it('reports discovery, empty, in-progress, and completion messages', () => {
    expect(conversionProgressTaskUpdate({ phase: 'discovering', completed: 0, total: 3, input: 'a.pdf' }, 'batch')).toMatchObject({
      message: 'Discovering PDFs…',
      completed: 0,
      total: 3,
      currentItem: 'a.pdf',
    });
    expect(conversionProgressTaskUpdate({ phase: 'converting', completed: 0, total: 0 }, 'batch').message).toBe('No PDFs found to convert.');
    expect(conversionProgressTaskUpdate({ phase: 'converting', completed: 0, total: 0 }, 'single').message).toBe('Converting…');
    expect(conversionProgressTaskUpdate({ phase: 'converting', completed: 1, total: 4 }, 'batch').message).toBe('2 of 4');
    expect(conversionProgressTaskUpdate({ phase: 'converting', completed: 4, total: 4 }, 'batch').message).toBe('Converted 4 of 4');
    expect(conversionProgressTaskUpdate({ phase: 'converting', completed: 1, total: 1 }, 'single').message).toBe('Converted');
    expect(conversionProgressTaskUpdate({ phase: 'preparing', completed: 0, total: 1, input: 'a.pdf' }, 'single').message)
      .toBe('Preparing Docling models…');
  });
});

describe('Docling prepare helpers', () => {
  it('detects Docling pipelines and confirms stop only while models are downloading', () => {
    expect(ingestPipelineIsDocling('docling')).toBe(true);
    expect(ingestPipelineIsDocling('docling:hybrid')).toBe(true);
    expect(ingestPipelineIsDocling('pymupdf')).toBe(false);
    expect(shouldConfirmDoclingPrepareStop('preparing')).toBe(true);
    expect(shouldConfirmDoclingPrepareStop('converting')).toBe(false);
    expect(DOCLING_PREPARE_STOP_CONFIRM).toContain('resume');
  });
});

describe('buildBatchConvertPayload', () => {
  it('sends selected paths instead of a directory when files are chosen', () => {
    expect(buildBatchConvertPayload({
      selectedPaths: ['C:\\docs\\a.pdf'],
      directory: 'C:\\docs',
      batchRecursive: true,
      batchOverwrite: false,
      embeddingModel: 'hashing',
      ingestPipeline: 'pymupdf',
      storeOriginal: true,
      pipelineOptions: { ocr: 'auto' },
      embedderOptions: { dimension: 256 },
    })).toEqual({
      action: SIDECAR_ACTIONS.batchConvert,
      paths: ['C:\\docs\\a.pdf'],
      overwrite: false,
      model: 'hashing',
      parser: 'pymupdf',
      store_original: true,
      pipeline_options: { ocr: 'auto' },
      embedder_options: { dimension: 256 },
    });
  });

  it('sends directory conversion options when no files are selected', () => {
    expect(buildBatchConvertPayload({
      selectedPaths: [],
      directory: 'C:\\docs',
      batchRecursive: false,
      batchOverwrite: true,
      embeddingModel: 'hashing',
      ingestPipeline: 'pymupdf',
      storeOriginal: false,
      pipelineOptions: {},
    })).toMatchObject({
      action: SIDECAR_ACTIONS.batchConvert,
      directory: 'C:\\docs',
      recursive: false,
      overwrite: true,
      store_original: false,
    });
  });
});

describe('conversion messages', () => {
  it('explains missing convert targets and sidecar failures', () => {
    expect(conversionMissingTargetMessage('selected')).toContain('Select one or more PDFs');
    expect(conversionMissingTargetMessage('batch')).toContain('Choose the directory');
    expect(conversionFailedMessage(true)).toBe('Selected PDF conversion failed');
    expect(conversionFailedMessage(false)).toBe('PDF directory conversion failed');
  });
});
