import { describe, expect, it } from 'vitest';
import { formatChunkingStrategy, formatOcrSummary } from './documentInfo';

describe('formatChunkingStrategy', () => {
  it('formats heading-aware sliding windows', () => {
    expect(formatChunkingStrategy('heading_block_sliding_window:500:75')).toBe(
      'Heading-aware sliding window · 500 words · 75 overlap',
    );
  });

  it('returns missing or unknown values as-is', () => {
    expect(formatChunkingStrategy()).toBe('-');
    expect(formatChunkingStrategy('fixed:400')).toBe('fixed:400');
  });
});

describe('formatOcrSummary', () => {
  it('reports when OCR was not recorded', () => {
    expect(formatOcrSummary()).toBe('Not recorded');
  });

  it('joins engine, mode, language, DPI, and page count', () => {
    expect(formatOcrSummary({
      ocr_engine: 'tesseract',
      ocr_mode: 'auto',
      ocr_language: 'eng',
      ocr_dpi: 300,
      ocr_pages: [1, 4],
    })).toBe('tesseract · Auto · eng · 300 DPI · 2 pages OCR’d');
  });

  it('singularizes a single OCR page', () => {
    expect(formatOcrSummary({ ocr_mode: 'force', ocr_pages: [2] })).toBe('Force · 1 page OCR’d');
  });
});
