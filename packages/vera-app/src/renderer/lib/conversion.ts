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

export const DOCLING_PREPARE_STOP_CONFIRM =
  'Docling is still downloading layout models. Stop will not cancel Hugging Face immediately — the download may keep going until this step finishes, and the next convert will resume. Stop anyway?';

export function ingestPipelineIsDocling(spec: string): boolean {
  return spec.trim().toLowerCase().startsWith('docling');
}

export function shouldConfirmDoclingPrepareStop(phase: string | undefined): boolean {
  return phase === 'preparing';
}

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
    return { ...base, message: 'Discovering PDFs…' };
  }
  if (event.phase === 'preparing') {
    return {
      ...base,
      message: 'Downloading Docling models (first run can take several minutes)…',
    };
  }
  if (!total) {
    return {
      ...base,
      message: mode === 'batch' ? 'No PDFs found to convert.' : 'Converting…',
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
  return {
    action: SIDECAR_ACTIONS.batchConvert,
    ...(options.selectedPaths.length
      ? { paths: options.selectedPaths }
      : { directory: options.directory, recursive: options.batchRecursive }),
    overwrite: options.batchOverwrite,
    model: options.embeddingModel,
    parser: options.ingestPipeline,
    store_original: options.storeOriginal,
    pipeline_options: options.pipelineOptions,
    ...(options.embedderOptions && Object.keys(options.embedderOptions).length
      ? { embedder_options: options.embedderOptions }
      : {}),
  };
}

export function conversionMissingTargetMessage(convertMode: ConvertMode): string {
  return convertMode === 'selected'
    ? 'Select one or more PDFs in Explorer (click, Ctrl/Cmd+click, or Shift+click).'
    : 'Choose the directory containing the PDFs to convert.';
}

export function conversionFailedMessage(hasSelectedPaths: boolean): string {
  return hasSelectedPaths ? 'Selected PDF conversion failed' : 'PDF directory conversion failed';
}
