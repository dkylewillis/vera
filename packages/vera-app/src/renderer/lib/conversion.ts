import { SIDECAR_ACTIONS } from '../../shared/protocol';
import type { BackgroundTask } from './backgroundTasks';
import type { BatchConvertResult, PipelineOptions, StreamEvent } from '../types';

/**
 * Wait for the sidecar request itself to settle, then end its active UI state
 * before callers perform slower follow-up work such as refreshing a library.
 */
export async function awaitConversionRequest<T>(
  request: Promise<T>,
  onSettled: () => void,
): Promise<T> {
  try {
    return await request;
  } finally {
    onSettled();
  }
}

export type ConversionProgressMode = 'single' | 'batch';
export type ConvertMode = 'batch' | 'selected';

export function conversionProgressTaskUpdate(
  event: Pick<StreamEvent, 'phase' | 'total' | 'completed' | 'input'>,
  mode: ConversionProgressMode,
): Partial<Omit<BackgroundTask, 'id' | 'kind'>> {
  const total = event.total ?? 0;
  const completed = event.completed ?? 0;
  const currentFile = event.input?.trim() || null;
  const base = {
    phase: event.phase,
    completed,
    total,
    currentItem: currentFile || undefined,
  };
  if (event.phase === 'discovering') {
    return { ...base, message: 'Discovering files…' };
  }
  if (event.phase === 'preparing') {
    return {
      ...base,
      message: 'Preparing…',
    };
  }
  if (!total) {
    return {
      ...base,
      message: mode === 'batch' ? 'No source files found to convert.' : 'Converting…',
    };
  }
  if (completed >= total) {
    return {
      ...base,
      message: mode === 'batch' ? `Converted ${completed} of ${total}` : 'Converted',
    };
  }
  return { ...base, message: `${completed + 1} of ${total}` };
}

function convertSharedFields(options: {
  selectedPaths: string[];
  embeddingModel: string;
  ingestPipeline: string;
  storeOriginal: boolean;
  pipelineOptions: PipelineOptions;
  embedderOptions?: PipelineOptions;
}): Record<string, unknown> {
  const selectedArePdfs = options.selectedPaths.length > 0
    && options.selectedPaths.every((path) => path.toLowerCase().endsWith('.pdf'));
  return {
    model: options.embeddingModel,
    ...(selectedArePdfs ? { parser: options.ingestPipeline } : {}),
    store_original: options.storeOriginal,
    pipeline_options: options.pipelineOptions,
    ...(options.embedderOptions && Object.keys(options.embedderOptions).length
      ? { embedder_options: options.embedderOptions }
      : {}),
  };
}

export function buildBatchConvertPayload(options: {
  selectedPaths: string[];
  directory: string;
  batchRecursive: boolean;
  batchOverwrite: boolean;
  embeddingModel: string;
  ingestPipeline: string;
  storeOriginal: boolean;
  pipelineOptions: PipelineOptions;
  embedderOptions?: PipelineOptions;
}): Record<string, unknown> {
  return {
    action: SIDECAR_ACTIONS.batchConvert,
    ...(options.selectedPaths.length
      ? { paths: options.selectedPaths }
      : { directory: options.directory, recursive: options.batchRecursive }),
    overwrite: options.batchOverwrite,
    ...convertSharedFields(options),
  };
}

export function buildSingleConvertPayload(options: {
  inputPath: string;
  outputPath: string;
  embeddingModel: string;
  ingestPipeline: string;
  storeOriginal: boolean;
  pipelineOptions: PipelineOptions;
  embedderOptions?: PipelineOptions;
}): Record<string, unknown> {
  return {
    action: SIDECAR_ACTIONS.convert,
    input: options.inputPath,
    output: options.outputPath,
    ...convertSharedFields({
      selectedPaths: [options.inputPath],
      embeddingModel: options.embeddingModel,
      ingestPipeline: options.ingestPipeline,
      storeOriginal: options.storeOriginal,
      pipelineOptions: options.pipelineOptions,
      embedderOptions: options.embedderOptions,
    }),
  };
}

export function singleConvertAsBatchResult(options: {
  outputPath: string;
  overwrite: boolean;
}): BatchConvertResult {
  const output = options.outputPath;
  const cut = Math.max(output.lastIndexOf('/'), output.lastIndexOf('\\'));
  return {
    directory: cut >= 0 ? output.slice(0, cut) : '',
    recursive: false,
    overwrite: options.overwrite,
    discovered: 1,
    converted: 1,
    skipped: 0,
    user_skipped: 0,
    malformed: 0,
    failed: 0,
    outputs: [output],
    skipped_existing: [],
    skipped_by_user: [],
    malformed_existing: [],
    errors: [],
  };
}

export function conversionMissingTargetMessage(convertMode: ConvertMode): string {
  return convertMode === 'selected'
    ? 'Select one or more PDFs or Markdown files in Explorer (click, Ctrl/Cmd+click, or Shift+click).'
    : 'Choose the directory containing the PDFs or Markdown files to convert.';
}

export function conversionFailedMessage(hasSelectedPaths: boolean): string {
  return hasSelectedPaths ? 'Selected file conversion failed' : 'Directory conversion failed';
}
