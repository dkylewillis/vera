import { describe, expect, it } from 'vitest';
import type { PipelineDescriptor } from '../../shared/contracts';
import {
  CUSTOM_EMBEDDING_VALUE,
  embeddingSelectValue,
  isKnownEmbeddingPreset,
  pipelineInstallHint,
  pipelineSelectOptions,
  presetOptionAvailable,
} from './convertPresets';

const pymupdfDescriptor: PipelineDescriptor = {
  provider: 'pymupdf',
  variant: '',
  spec: 'pymupdf',
  label: 'pymupdf — built-in (default)',
  description: 'Built-in PDF ingest pipeline',
  installed: true,
  capabilities: {},
  fields: [
    {
      key: 'chunk_size',
      label: 'Chunk size',
      type: 'integer',
      default: 500,
    },
  ],
};

const doclingDescriptor: PipelineDescriptor = {
  provider: 'docling',
  variant: 'hybrid',
  spec: 'docling',
  label: 'docling — HybridChunker',
  description: 'Docling HybridChunker',
  installed: true,
  capabilities: { overlap_supported: false },
  fields: [
    {
      key: 'chunk_size',
      label: 'Chunk size',
      type: 'integer',
      default: 500,
      unit: 'tokens',
    },
  ],
};

describe('convertPresets', () => {
  it('treats hashing and MiniLM specs as known presets', () => {
    expect(isKnownEmbeddingPreset('hashing')).toBe(true);
    expect(isKnownEmbeddingPreset('sentence-transformers:all-MiniLM-L6-v2')).toBe(true);
    expect(isKnownEmbeddingPreset('openai:text-embedding-3-small')).toBe(false);
  });

  it('maps unknown models to the custom select value', () => {
    expect(embeddingSelectValue('hashing')).toBe('hashing');
    expect(embeddingSelectValue('openai:text-embedding-3-small')).toBe(CUSTOM_EMBEDDING_VALUE);
  });

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
    const withDocling = pipelineSelectOptions([pymupdfDescriptor, doclingDescriptor]);
    expect(withDocling.map((option) => option.value)).toEqual(['pymupdf', 'docling']);

    const withoutDocling = pipelineSelectOptions([pymupdfDescriptor]);
    expect(withoutDocling.map((option) => option.value)).toEqual(['pymupdf', 'docling']);
    expect(withoutDocling[1]?.requiresProvider).toBe('docling');
  });

  it('returns install hints for missing optional pipelines', () => {
    expect(pipelineInstallHint('docling', [pymupdfDescriptor])).toContain('uv sync --extra docling');
    expect(pipelineInstallHint('pymupdf', [pymupdfDescriptor])).toBe('Built-in PDF ingest pipeline');
  });
});
