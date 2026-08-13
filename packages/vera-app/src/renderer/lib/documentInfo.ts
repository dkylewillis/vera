import type { InspectResult } from '../types';

export function formatChunkingStrategy(value?: string): string {
  if (!value) return '-';
  const match = /^heading_block_sliding_window:(\d+):(\d+)$/.exec(value);
  if (!match) return value;
  return `Heading-aware sliding window · ${match[1]} words · ${match[2]} overlap`;
}

export function formatOcrSummary(ocr?: InspectResult['ocr']): string {
  if (!ocr) return 'Not recorded';
  const pages = ocr.ocr_pages ?? [];
  const mode = ocr.ocr_mode ? `${ocr.ocr_mode[0].toUpperCase()}${ocr.ocr_mode.slice(1)}` : 'Unknown mode';
  const details = [
    ocr.ocr_engine,
    mode,
    ocr.ocr_language,
    ocr.ocr_dpi ? `${ocr.ocr_dpi} DPI` : null,
    `${pages.length} page${pages.length === 1 ? '' : 's'} OCR’d`,
  ].filter(Boolean);
  return details.join(' · ');
}
