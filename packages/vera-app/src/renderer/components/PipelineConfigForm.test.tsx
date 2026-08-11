import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type { PipelineDescriptor } from '../../shared/contracts';
import { mergePipelineFieldValues, PipelineConfigForm } from './PipelineConfigForm';

const pymupdfDescriptor: PipelineDescriptor = {
  provider: 'pymupdf',
  variant: '',
  spec: 'pymupdf',
  label: 'pymupdf',
  description: 'Built-in',
  installed: true,
  capabilities: {},
  fields: [
    {
      key: 'chunk_size',
      label: 'Chunk size',
      type: 'integer',
      default: 500,
      unit: 'characters',
      minimum: 100,
      maximum: 3000,
      step: 50,
    },
    {
      key: 'overlap',
      label: 'Overlap',
      type: 'integer',
      default: 75,
      unit: 'characters',
    },
    {
      key: 'ocr_mode',
      label: 'OCR mode',
      type: 'enum',
      default: 'auto',
      choices: [
        { value: 'auto', label: 'Auto' },
        { value: 'off', label: 'Off' },
        { value: 'force', label: 'Force' },
      ],
    },
    {
      key: 'ocr_language',
      label: 'OCR language',
      type: 'enum',
      default: 'eng',
      allow_custom: true,
      placeholder: 'eng',
      choices: [
        { value: 'eng', label: 'English (eng)' },
        { value: 'spa', label: 'Spanish (spa)' },
        { value: 'fra', label: 'French (fra)' },
      ],
    },
  ],
};

const doclingDescriptor: PipelineDescriptor = {
  provider: 'docling',
  variant: 'hybrid',
  spec: 'docling',
  label: 'docling',
  description: 'Docling',
  installed: true,
  capabilities: { overlap_supported: false, ocr_dpi_supported: false },
  fields: [
    {
      key: 'chunk_size',
      label: 'Chunk size',
      type: 'integer',
      default: 500,
      unit: 'tokens',
    },
    {
      key: 'ocr_language',
      label: 'OCR language',
      type: 'string',
      default: 'en',
      placeholder: 'en',
    },
  ],
  notes: ['Overlap is not applied by Docling HybridChunker.'],
};

describe('PipelineConfigForm', () => {
  it('merges saved values over descriptor defaults', () => {
    expect(mergePipelineFieldValues(pymupdfDescriptor, { chunk_size: 800 })).toEqual({
      chunk_size: 800,
      overlap: 75,
      ocr_mode: 'auto',
      ocr_language: 'eng',
    });
  });

  it('renders PyMuPDF fields including overlap and OCR mode', () => {
    const html = renderToStaticMarkup(
      <PipelineConfigForm
        descriptor={pymupdfDescriptor}
        values={mergePipelineFieldValues(pymupdfDescriptor, {})}
        onChange={() => undefined}
      />,
    );
    expect(html).toContain('Overlap (characters)');
    expect(html).toContain('OCR mode');
    expect(html).toContain('OCR language');
    expect(html).toContain('Spanish (spa)');
    expect(html).toContain('Custom…');
    expect(html).toContain('value="500"');
    expect(html).toContain('value="75"');
  });

  it('shows a custom OCR language text field for combinations', () => {
    const html = renderToStaticMarkup(
      <PipelineConfigForm
        descriptor={pymupdfDescriptor}
        values={mergePipelineFieldValues(pymupdfDescriptor, { ocr_language: 'eng+spa' })}
        onChange={() => undefined}
      />,
    );
    expect(html).toContain('value="eng+spa"');
    expect(html).toContain('aria-label="OCR language custom value"');
  });

  it('omits overlap for Docling and shows notes', () => {
    const html = renderToStaticMarkup(
      <PipelineConfigForm
        descriptor={doclingDescriptor}
        values={mergePipelineFieldValues(doclingDescriptor, {})}
        onChange={() => undefined}
      />,
    );
    expect(html).toContain('Chunk size (tokens)');
    expect(html).not.toContain('Overlap (characters)');
    expect(html).not.toContain('>Overlap<');
    expect(html).toContain('Overlap is not applied by Docling HybridChunker.');
  });
});
