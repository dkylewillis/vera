import { siblingPdfPath, siblingSourcePath, sameFsPath } from './formatting';
import { explorerEntryType } from './explorer';
import type { InspectResult, PipelineOptions } from '../types';

export type ReconvertSourceResolution =
  | { status: 'ready'; sourcePath: string }
  | { status: 'export'; sourcePath: string }
  | { status: 'unavailable' };

/** @deprecated Use ReconvertSourceResolution; pdfPath aliases sourcePath. */
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

const CONVERTIBLE_TYPES = ['pdf', 'md'] as const;

function sourceStem(path: string): string {
  return path.replace(/\.(vera|pdf|md|markdown)$/i, '');
}

function expectedEntryType(sourceFileName?: string | null): 'pdf' | 'md' | null {
  const name = sourceFileName?.trim();
  if (!name) return null;
  const type = explorerEntryType(name);
  return type === 'pdf' || type === 'md' ? type : null;
}

/** Locate the sibling source already listed next to a `.vera` archive. */
export function findSiblingSourcePath(
  veraPath: string,
  entries: Array<{ path: string; type: string }>,
  sourceFileName?: string | null,
): string | null {
  const sibling = siblingSourcePath(veraPath, sourceFileName);
  const expectedType = expectedEntryType(sourceFileName) ?? explorerEntryType(sibling);
  if (sibling) {
    const listed = entries.find((entry) => {
      if (!sameFsPath(entry.path, sibling)) return false;
      if (expectedType === 'pdf' || expectedType === 'md') return entry.type === expectedType;
      return entry.type === 'pdf' || entry.type === 'md';
    });
    if (listed) return listed.path;
  }
  if (sourceFileName?.trim()) return null;
  const veraStem = sourceStem(veraPath);
  for (const type of CONVERTIBLE_TYPES) {
    const listed = entries.find(
      (entry) => entry.type === type && sameFsPath(sourceStem(entry.path), veraStem),
    );
    if (listed) return listed.path;
  }
  return null;
}

/** Locate the sibling PDF already listed next to a `.vera` archive. */
export function findSiblingPdfPath(
  veraPath: string,
  entries: Array<{ path: string; type: string }>,
): string | null {
  return findSiblingSourcePath(veraPath, entries);
}

/**
 * Decide how Reconvert should obtain a source file: use a sibling on disk,
 * export the embedded original to that sibling path, or give up.
 */
export function resolveReconvertSource(
  veraPath: string,
  options: {
    entries?: Array<{ path: string; type: string }>;
    siblingExists?: boolean;
    sourceFileName?: string | null;
  } = {},
): ReconvertSourceResolution {
  const sibling = siblingSourcePath(veraPath, options.sourceFileName);
  if (!sibling) return { status: 'unavailable' };
  const listed = findSiblingSourcePath(
    veraPath,
    options.entries ?? [],
    options.sourceFileName,
  );
  if (listed) return { status: 'ready', sourcePath: listed };
  if (options.siblingExists) return { status: 'ready', sourcePath: sibling };
  return { status: 'export', sourcePath: sibling };
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
    sourceFileName?: string | null;
  } = {},
): ReconvertPdfResolution {
  const resolved = resolveReconvertSource(veraPath, options);
  if (resolved.status === 'unavailable') return resolved;
  return { status: resolved.status, pdfPath: resolved.sourcePath };
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

export function reconvertMissingSourceMessage(
  veraPath: string,
  sourceFileName?: string | null,
): string {
  const sibling = siblingSourcePath(veraPath, sourceFileName) || siblingPdfPath(veraPath);
  const name = sibling.split(/[/\\]/).pop() || 'the matching source file';
  return `Reconvert needs ${name} beside this archive, or an embedded original to restore. Place the source file next to the .vera file, or export the original from Document Info.`;
}
