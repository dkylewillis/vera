import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  fallbackPipelineDescriptors,
  loadEmbeddingDescriptors,
  loadIngestPipelineDescriptors,
} from '../hooks/useAppBootstrap';

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('fallbackPipelineDescriptors', () => {
  it('wraps pipeline names as installed descriptors', () => {
    expect(fallbackPipelineDescriptors(['pymupdf', 'docling'])).toEqual([
      {
        provider: 'pymupdf',
        variant: '',
        spec: 'pymupdf',
        label: 'pymupdf',
        description: '',
        installed: true,
        capabilities: {},
        fields: [],
        notes: [],
        source: 'bundled',
      },
      {
        provider: 'docling',
        variant: '',
        spec: 'docling',
        label: 'docling',
        description: '',
        installed: true,
        capabilities: {},
        fields: [],
        notes: [],
        source: 'bundled',
      },
    ]);
  });
});

describe('loadEmbeddingDescriptors', () => {
  it('returns providers from describe_embedding_providers', async () => {
    vi.stubGlobal('window', {
      vera: {
        request: vi.fn(async () => ({
          ok: true,
          result: { providers: [{ provider: 'openai', label: 'OpenAI', description: '', installed: true, fields: [] }] },
        })),
      },
    });
    const providers = await loadEmbeddingDescriptors();
    expect(providers).toEqual([
      { provider: 'openai', label: 'OpenAI', description: '', installed: true, fields: [] },
    ]);
  });

  it('returns an empty list when describe fails', async () => {
    vi.stubGlobal('window', {
      vera: {
        request: vi.fn(async () => ({ ok: false, error: 'sidecar down' })),
      },
    });
    await expect(loadEmbeddingDescriptors()).resolves.toEqual([]);
  });
});

describe('loadIngestPipelineDescriptors', () => {
  it('falls back to listed pipeline names when describe is empty', async () => {
    const request = vi.fn(async (payload: { action: string }) => {
      if (payload.action === 'describe_ingest_pipelines') {
        return { ok: true, result: { pipelines: [] } };
      }
      return { ok: true, result: { pipelines: ['pymupdf', 'docling'] } };
    });
    vi.stubGlobal('window', { vera: { request } });
    const descriptors = await loadIngestPipelineDescriptors();
    expect(descriptors.map((item) => item.provider)).toEqual(['pymupdf', 'docling']);
    expect(descriptors[0].source).toBe('bundled');
    expect(descriptors[1].source).toBe('bundled');
  });

  it('falls back to pymupdf when both describe and list fail', async () => {
    vi.stubGlobal('window', {
      vera: {
        request: vi.fn(async () => ({ ok: false })),
      },
    });
    const descriptors = await loadIngestPipelineDescriptors();
    expect(descriptors).toEqual(fallbackPipelineDescriptors(['pymupdf']));
  });
});
