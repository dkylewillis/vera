import { describe, expect, it } from 'vitest';
import type { PipelineDescriptor } from '../../shared/contracts';
import {
  CUSTOM_EMBEDDING_VALUE,
  EMBEDDING_MODEL_PRESETS,
  embeddingProviderFromSpec,
  embeddingSelectOptions,
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
  label: 'pymupdf — default PDF pipeline',
  description: 'Default PDF ingest pipeline',
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
  label: 'Advanced layout (slower)',
  description: 'Docling HybridChunker. Slower than PyMuPDF; better tables, layout, and scanned pages.',
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
    expect(EMBEDDING_MODEL_PRESETS.find((item) => item.value === 'sentence-transformers:all-MiniLM-L6-v2')?.label)
      .toBe('Local semantic (MiniLM)');
    expect(isKnownEmbeddingPreset('openai:text-embedding-3-small')).toBe(false);
  });

  it('parses provider names from embedding specs', () => {
    expect(embeddingProviderFromSpec('hashing')).toBe('hashing');
    expect(embeddingProviderFromSpec('sentence-transformers:all-MiniLM-L6-v2')).toBe('sentence-transformers');
    expect(embeddingProviderFromSpec('openai:text-embedding-3-small')).toBe('openai');
  });

  it('adds external embedder options after bundled presets', () => {
    const options = embeddingSelectOptions([
      {
        provider: 'hashing',
        label: 'hashing',
        description: '',
        installed: true,
        fields: [],
        source: 'bundled',
      },
      {
        provider: 'openai',
        label: 'OpenAI',
        description: '',
        installed: true,
        default_model_id: 'text-embedding-3-small',
        fields: [],
        source: 'external',
      },
    ]);
    expect(options.some((item) => item.value === 'openai:text-embedding-3-small' && item.source === 'external')).toBe(true);
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

  it('treats a discovered but uninstalled Docling descriptor as a missing hint', () => {
    const options = pipelineSelectOptions([
      pymupdfDescriptor,
      { ...doclingDescriptor, installed: false },
    ]);
    expect(options.map((option) => option.value)).toEqual(['pymupdf', 'docling']);
    expect(options[1]?.requiresProvider).toBe('docling');
    expect(pipelineInstallHint('docling', [
      pymupdfDescriptor,
      { ...doclingDescriptor, installed: false },
    ])).toContain('vera-cli[docling]');
  });

  it('preserves bundled source on installed options', () => {
    const options = pipelineSelectOptions([
      { ...pymupdfDescriptor, source: 'bundled' },
      { ...doclingDescriptor, source: 'bundled' },
    ]);
    expect(options[0]?.source).toBe('bundled');
    expect(options[1]?.source).toBe('bundled');
  });

  it('returns install hints for missing optional pipelines', () => {
    expect(pipelineInstallHint('docling', [pymupdfDescriptor])).toContain('vera-cli[docling]');
    expect(pipelineInstallHint('docling', [pymupdfDescriptor])).toContain('uv sync --extra docling');
    expect(pipelineInstallHint('pymupdf', [pymupdfDescriptor])).toBe('Default PDF ingest pipeline');
  });
});
