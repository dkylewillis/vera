import { describe, expect, it } from 'vitest';
import {
  findSiblingPdfPath,
  reconvertMissingSourceMessage,
  reconvertPrefillFromInspect,
  resolveReconvertPdf,
} from './reconvert';

describe('resolveReconvertPdf', () => {
  const veraPath = 'C:\\library\\manual.vera';

  it('prefers a listed sibling PDF', () => {
    expect(resolveReconvertPdf(veraPath, {
      entries: [
        { path: 'C:\\library\\other.pdf', type: 'pdf' },
        { path: 'C:\\library\\manual.pdf', type: 'pdf' },
      ],
    })).toEqual({ status: 'ready', pdfPath: 'C:\\library\\manual.pdf' });
  });

  it('matches a listed sibling case-insensitively', () => {
    expect(findSiblingPdfPath(veraPath, [
      { path: 'C:\\library\\Manual.PDF', type: 'pdf' },
    ])).toBe('C:\\library\\Manual.PDF');
  });

  it('uses a sibling that exists on disk but is not in the listing', () => {
    expect(resolveReconvertPdf(veraPath, { siblingExists: true })).toEqual({
      status: 'ready',
      pdfPath: 'C:\\library\\manual.pdf',
    });
  });

  it('asks to export the embedded original when no sibling is present', () => {
    expect(resolveReconvertPdf(veraPath, {
      entries: [{ path: veraPath, type: 'vera' }],
      siblingExists: false,
    })).toEqual({ status: 'export', pdfPath: 'C:\\library\\manual.pdf' });
  });

  it('is unavailable for non-archive paths', () => {
    expect(resolveReconvertPdf('C:\\library\\manual.pdf')).toEqual({ status: 'unavailable' });
  });
});

describe('reconvertPrefillFromInspect', () => {
  it('reads parser and embedding from inspect metadata', () => {
    expect(reconvertPrefillFromInspect({
      parser_name: 'docling',
      default_embedding_model: 'sentence-transformers:all-MiniLM-L6-v2',
      source_attachment_id: 'source_original',
    })).toEqual({
      embeddingModel: 'sentence-transformers:all-MiniLM-L6-v2',
      ingestPipeline: 'docling',
      hasEmbeddedSource: true,
    });
  });

  it('falls back to embedding_model and embedding_models', () => {
    expect(reconvertPrefillFromInspect({
      embedding_model: 'hashing',
      embedding_models: ['hashing'],
    })).toEqual({
      embeddingModel: 'hashing',
      ingestPipeline: null,
      hasEmbeddedSource: false,
    });
  });

  it('handles a missing inspect payload', () => {
    expect(reconvertPrefillFromInspect(null)).toEqual({
      embeddingModel: null,
      ingestPipeline: null,
      hasEmbeddedSource: false,
    });
  });
});

describe('reconvertMissingSourceMessage', () => {
  it('names the expected sibling PDF', () => {
    expect(reconvertMissingSourceMessage('C:\\docs\\manual.vera')).toContain('manual.pdf');
  });
});
