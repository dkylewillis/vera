import { describe, expect, it } from 'vitest';
import type { PipelineDescriptor } from '../../shared/contracts';
import {
  pipelineInstallHint,
  pipelineSelectOptions,
  presetOptionAvailable,
} from './convertPresets';

const pymupdf: PipelineDescriptor = {
  provider: 'pymupdf',
  spec: 'pymupdf',
  label: 'pymupdf — default PDF pipeline',
  description: 'Bundled PyMuPDF parser',
  installed: true,
  source: 'bundled',
};

const docling: PipelineDescriptor = {
  provider: 'docling',
  spec: 'docling',
  label: 'docling — HybridChunker',
  description: 'Docling HybridChunker',
  installed: true,
  source: 'external',
};

describe('convertPresets', () => {
  it('gates optional providers on sidecar availability', () => {
    expect(presetOptionAvailable(
      { value: 'docling', label: 'docling', requiresProvider: 'docling' },
      ['pymupdf'],
    )).toBe(false);
    expect(presetOptionAvailable(
      { value: 'docling', label: 'docling', requiresProvider: 'docling' },
      ['pymupdf', 'docling'],
    )).toBe(true);
  });

  it('builds select options from descriptors and missing install hints', () => {
    expect(pipelineSelectOptions([pymupdf, docling]).map((option) => option.value)).toEqual([
      'pymupdf',
      'docling',
    ]);
    const withoutDocling = pipelineSelectOptions([pymupdf]);
    expect(withoutDocling.map((option) => option.value)).toEqual(['pymupdf', 'docling']);
    expect(withoutDocling[1]?.requiresProvider).toBe('docling');
    expect(pipelineSelectOptions([pymupdf, docling])[1]?.source).toBe('external');
    expect(presetOptionAvailable(withoutDocling[1]!, ['pymupdf'])).toBe(false);
  });

  it('returns packaged-aware install hints for missing optional pipelines', () => {
    expect(pipelineInstallHint('docling', [pymupdf])).toContain('python -m pip install vera-ingest-docling');
    expect(pipelineInstallHint('pymupdf', [pymupdf])).toBe('Bundled PyMuPDF parser');
  });
});
