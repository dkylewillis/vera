import { SIDECAR_ACTIONS } from '../../shared/protocol';
import type { BackgroundTask } from './backgroundTasks';
import type { PipelineOptions, StreamEvent } from '../types';

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
  const selectedArePdfs = options.selectedPaths.length > 0
    && options.selectedPaths.every((path) => path.toLowerCase().endsWith('.pdf'));
  return {
    action: SIDECAR_ACTIONS.batchConvert,
    ...(options.selectedPaths.length
      ? { paths: options.selectedPaths }
      : { directory: options.directory, recursive: options.batchRecursive }),
    overwrite: options.batchOverwrite,
    model: options.embeddingModel,
    ...(selectedArePdfs ? { parser: options.ingestPipeline } : {}),
    store_original: options.storeOriginal,
    pipeline_options: options.pipelineOptions,
    ...(options.embedderOptions && Object.keys(options.embedderOptions).length
      ? { embedder_options: options.embedderOptions }
      : {}),
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
