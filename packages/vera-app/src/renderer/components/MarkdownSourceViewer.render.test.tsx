import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { MarkdownDocument, MarkdownHtmlDocument } from './MarkdownSourceViewer';

describe('MarkdownHtmlDocument', () => {
  it('inserts the sidecar HTML as-is', () => {
    const html = renderToStaticMarkup(
      <MarkdownHtmlDocument html={'<h1 data-ls="1" data-le="1">Title</h1>'} highlighted={new Set([1])} />,
    );
    expect(html).toContain('<h1 data-ls="1" data-le="1">Title</h1>');
  });
});

describe('MarkdownDocument', () => {
  it('renders a short document and highlights the cited table', () => {
    const html = renderToStaticMarkup(
      <MarkdownDocument
        text={['Intro', '', '| A | B |', '| --- | --- |', '| 1 | 2 |'].join('\n')}
        highlighted={new Set([4])}
      />,
    );
    expect(html).toContain('<table');
    expect(html).toContain('is-highlighted');
  });

  it('renders the whole document', () => {
    const text = Array.from({ length: 40 }, (_, index) => `Paragraph ${index} stays readable.`).join('\n\n');
    const html = renderToStaticMarkup(
      <MarkdownDocument text={text} highlighted={new Set()} />,
    );
    expect(html).toContain('Paragraph 0 stays readable.');
    expect(html).toContain('Paragraph 39 stays readable.');
  });
});
