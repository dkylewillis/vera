import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type { EmbedderDescriptor } from '../../shared/contracts';
import { EmbedderConfigForm, embedderAsPipelineDescriptor } from './EmbedderConfigForm';

const openaiDescriptor: EmbedderDescriptor = {
  provider: 'openai',
  label: 'OpenAI',
  description: 'Remote embeddings',
  installed: true,
  default_model_id: 'text-embedding-3-small',
  fields: [
    {
      key: 'batch_size',
      label: 'Batch size',
      type: 'integer',
      default: 16,
    },
  ],
  notes: ['needs a key'],
  source: 'external',
  capabilities: { requires_api_key: true, credential_env: 'OPENAI_API_KEY' },
};

describe('embedderAsPipelineDescriptor', () => {
  it('returns null for a missing embedder', () => {
    expect(embedderAsPipelineDescriptor(null)).toBeNull();
    expect(embedderAsPipelineDescriptor(undefined)).toBeNull();
  });

  it('maps embedder metadata onto the pipeline form descriptor', () => {
    expect(embedderAsPipelineDescriptor(openaiDescriptor)).toEqual({
      provider: 'openai',
      variant: '',
      spec: 'openai',
      label: 'OpenAI',
      description: 'Remote embeddings',
      installed: true,
      capabilities: {},
      fields: openaiDescriptor.fields,
      notes: ['needs a key'],
      source: 'external',
    });
  });
});

describe('EmbedderConfigForm', () => {
  it('renders mapped embedder fields', () => {
    const html = renderToStaticMarkup(
      <EmbedderConfigForm
        descriptor={openaiDescriptor}
        values={{ batch_size: 8 }}
        onChange={() => undefined}
      />,
    );
    expect(html).toContain('Batch size');
  });
});
