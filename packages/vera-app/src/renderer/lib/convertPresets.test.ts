import { describe, expect, it } from 'vitest';
import {
  CUSTOM_EMBEDDING_VALUE,
  embeddingSelectValue,
  isKnownEmbeddingPreset,
  mergePipelineOptions,
  presetOptionAvailable,
} from './convertPresets';

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

  it('keeps presets first and appends unknown installed pipelines', () => {
    const merged = mergePipelineOptions(['pymupdf', 'docling', 'example']);
    expect(merged.map((option) => option.value)).toEqual(['pymupdf', 'docling', 'example']);
  });
});
