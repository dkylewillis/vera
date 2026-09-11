import { describe, expect, it } from 'vitest';
import { markdownDisplayLines } from './MarkdownSourceViewer';

describe('markdownDisplayLines', () => {
  it('strips a leading UTF-8 BOM so line numbers match ingest locators', () => {
    expect(markdownDisplayLines('\ufeff# Title\n\nBody')).toEqual(['# Title', '', 'Body']);
  });

  it('keeps ordinary Markdown unchanged', () => {
    expect(markdownDisplayLines('# Title\n\nBody')).toEqual(['# Title', '', 'Body']);
  });
});
