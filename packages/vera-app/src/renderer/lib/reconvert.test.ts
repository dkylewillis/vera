import { describe, expect, it } from 'vitest';
import {
  findSiblingPdfPath,
  reconvertExportGate,
  reconvertInspectFailedMessage,
  reconvertMissingSourceMessage,
  reconvertPipelineOptionsFromInspect,
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

describe('reconvertPipelineOptionsFromInspect', () => {
  it('maps nested OCR and PyMuPDF sliding-window chunking onto pipeline options', () => {
    expect(reconvertPipelineOptionsFromInspect({
      chunking_strategy: 'heading_block_sliding_window:800:120',
      ocr: {
        ocr_mode: 'force',
        ocr_language: 'eng+spa',
        ocr_dpi: 200,
      },
    })).toEqual({
      ocr_mode: 'force',
      ocr_language: 'eng+spa',
      ocr_dpi: 200,
      chunk_size: 800,
      overlap: 120,
    });
  });

  it('maps Docling hybrid chunk size and prefers nested OCR over top-level aliases', () => {
    expect(reconvertPipelineOptionsFromInspect({
      chunking_strategy: 'docling_hybrid:640',
      ocr_mode: 'off',
      ocr_language: 'eng',
      ocr_dpi: '300',
      ocr: {
        ocr_mode: 'auto',
        ocr_language: 'en',
      },
    })).toEqual({
      ocr_mode: 'auto',
      ocr_language: 'en',
      ocr_dpi: 300,
      chunk_size: 640,
    });
  });

  it('returns an empty object when inspect has no pipeline metadata', () => {
    expect(reconvertPipelineOptionsFromInspect(null)).toEqual({});
    expect(reconvertPipelineOptionsFromInspect({ parser_name: 'pymupdf' })).toEqual({});
  });
});

describe('reconvertExportGate', () => {
  it('blocks export when inspect fails unless an embedded source is already known', () => {
    expect(reconvertExportGate({ inspectOk: false, hasEmbeddedSource: false })).toEqual({
      allow: false,
      reason: 'inspect-failed',
    });
    expect(reconvertExportGate({ inspectOk: false, hasEmbeddedSource: true })).toEqual({ allow: true });
  });

  it('blocks export when inspect succeeded but the archive has no embedded source', () => {
    expect(reconvertExportGate({ inspectOk: true, hasEmbeddedSource: false })).toEqual({
      allow: false,
      reason: 'missing-source',
    });
    expect(reconvertExportGate({ inspectOk: true, hasEmbeddedSource: true })).toEqual({ allow: true });
  });
});

describe('reconvertInspectFailedMessage', () => {
  it('uses a distinct metadata-read error, including sidecar detail when present', () => {
    expect(reconvertInspectFailedMessage()).toBe('Could not read archive metadata.');
    expect(reconvertInspectFailedMessage('database is locked')).toBe(
      'Could not read archive metadata: database is locked',
    );
  });
});

describe('reconvertMissingSourceMessage', () => {
  it('names the expected sibling PDF', () => {
    expect(reconvertMissingSourceMessage('C:\\docs\\manual.vera')).toContain('manual.pdf');
  });
});
