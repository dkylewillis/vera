import { siblingPdfPath, sameFsPath } from './formatting';
import type { InspectResult, PipelineOptions } from '../types';

export type ReconvertPdfResolution =
  | { status: 'ready'; pdfPath: string }
  | { status: 'export'; pdfPath: string }
  | { status: 'unavailable' };

export type ReconvertPrefill = {
  embeddingModel: string | null;
  ingestPipeline: string | null;
  hasEmbeddedSource: boolean;
};

export type ReconvertExportGate =
  | { allow: true }
  | { allow: false; reason: 'inspect-failed' | 'missing-source' };

/** Locate the sibling PDF already listed next to a `.vera` archive. */
export function findSiblingPdfPath(
  veraPath: string,
  entries: Array<{ path: string; type: string }>,
): string | null {
  const sibling = siblingPdfPath(veraPath);
  if (!sibling) return null;
  return entries.find((entry) => entry.type === 'pdf' && sameFsPath(entry.path, sibling))?.path ?? null;
}

/**
 * Decide how Reconvert should obtain a PDF: use a sibling on disk, export the
 * embedded original to that sibling path, or give up.
 */
export function resolveReconvertPdf(
  veraPath: string,
  options: {
    entries?: Array<{ path: string; type: string }>;
    siblingExists?: boolean;
  } = {},
): ReconvertPdfResolution {
  const sibling = siblingPdfPath(veraPath);
  if (!sibling) return { status: 'unavailable' };
  const listed = findSiblingPdfPath(veraPath, options.entries ?? []);
  if (listed) return { status: 'ready', pdfPath: listed };
  if (options.siblingExists) return { status: 'ready', pdfPath: sibling };
  return { status: 'export', pdfPath: sibling };
}

export function reconvertPrefillFromInspect(
  inspect: InspectResult | null | undefined,
): ReconvertPrefill {
  const embeddingModel = inspect?.default_embedding_model?.trim()
    || inspect?.embedding_model?.trim()
    || inspect?.embedding_models?.[0]?.trim()
    || null;
  const ingestPipeline = inspect?.parser_name?.trim() || null;
  const hasEmbeddedSource = Boolean(inspect?.source_attachment_id);
  return { embeddingModel, ingestPipeline, hasEmbeddedSource };
}

function finiteNumber(value: unknown): number | undefined {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return undefined;
}

/**
 * Map archive inspect OCR/chunking metadata onto ingest pipeline option keys.
 * Callers merge this over saved pipeline configs so reconvert restores the
 * archive's settings instead of global Convert defaults.
 */
export function reconvertPipelineOptionsFromInspect(
  inspect: InspectResult | null | undefined,
): PipelineOptions {
  if (!inspect) return {};
  const options: PipelineOptions = {};
  const ocr = inspect.ocr;
  const ocrMode = ocr?.ocr_mode ?? inspect.ocr_mode;
  const ocrLanguage = ocr?.ocr_language ?? inspect.ocr_language;
  const ocrDpi = finiteNumber(ocr?.ocr_dpi ?? inspect.ocr_dpi);
  if (ocrMode) options.ocr_mode = ocrMode;
  if (ocrLanguage) options.ocr_language = ocrLanguage;
  if (ocrDpi !== undefined) options.ocr_dpi = ocrDpi;

  const chunking = inspect.chunking_strategy?.trim() || '';
  const sliding = /^heading_block_sliding_window:(\d+):(\d+)$/.exec(chunking);
  if (sliding) {
    options.chunk_size = Number(sliding[1]);
    options.overlap = Number(sliding[2]);
    return options;
  }
  const hybrid = /^docling_hybrid:(\d+)$/.exec(chunking);
  if (hybrid) {
    options.chunk_size = Number(hybrid[1]);
  }
  return options;
}

/**
 * Exporting an embedded source requires inspect metadata (or other proof of an
 * embedded original). A failed inspect must not proceed to export.
 */
export function reconvertExportGate(options: {
  inspectOk: boolean;
  hasEmbeddedSource: boolean;
}): ReconvertExportGate {
  if (options.hasEmbeddedSource) return { allow: true };
  if (!options.inspectOk) return { allow: false, reason: 'inspect-failed' };
  return { allow: false, reason: 'missing-source' };
}

export function reconvertInspectFailedMessage(error?: string | null): string {
  const detail = error?.trim();
  return detail
    ? `Could not read archive metadata: ${detail}`
    : 'Could not read archive metadata.';
}

export function reconvertMissingSourceMessage(veraPath: string): string {
  const sibling = siblingPdfPath(veraPath);
  const name = sibling.split(/[/\\]/).pop() || 'the matching .pdf';
  return `Reconvert needs ${name} beside this archive, or an embedded source PDF to restore. Place the PDF next to the .vera file, or export the original from Document Info.`;
}
