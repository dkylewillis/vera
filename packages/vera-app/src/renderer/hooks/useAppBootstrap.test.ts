import { describe, expect, it } from 'vitest';
import { fallbackPipelineDescriptors } from '../hooks/useAppBootstrap';

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
        source: 'external',
      },
    ]);
  });
});
