import { siblingPdfPath, sameFsPath } from './formatting';
import type { InspectResult } from '../types';

export type ReconvertPdfResolution =
  | { status: 'ready'; pdfPath: string }
  | { status: 'export'; pdfPath: string }
  | { status: 'unavailable' };

export type ReconvertPrefill = {
  embeddingModel: string | null;
  ingestPipeline: string | null;
  hasEmbeddedSource: boolean;
};

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

export function reconvertMissingSourceMessage(veraPath: string): string {
  const sibling = siblingPdfPath(veraPath);
  const name = sibling.split(/[/\\]/).pop() || 'the matching .pdf';
  return `Reconvert needs ${name} beside this archive, or an embedded source PDF to restore. Place the PDF next to the .vera file, or export the original from Document Info.`;
}
