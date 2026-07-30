import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { ChatTurn } from './ChatTurn';
import type { ChatCitationResult, SessionTurn } from '../types';

function citation(id: string): ChatCitationResult {
  return {
    id,
    label: `[${id}] p. 117`,
    result: {
      chunk_id: `chunk_${id}`,
      score: 0.9,
      text: 'Detention basins shall be sized for the 25-year storm.',
      page_start: 117,
      page_end: 117,
      heading_path: 'Chapter 4 > 4.2 Detention Design',
      source_filename: 'manual.pdf',
      document_id: 'document_0001',
    },
  };
}

// The activity trace renders its own markup (including `<code>` pills), so assert
// against the answer body only.
function renderAnswer(content: string, citations: ChatCitationResult[] = [citation('C1')]) {
  const turn: SessionTurn = { role: 'assistant', content, citations, timestamp: 0 };
  const html = renderToStaticMarkup(
    <ChatTurn turn={turn} selectCitation={() => {}} showTrace={false} />,
  );
  return html.slice(html.indexOf('<div class="markdownBody">'));
}

describe('ChatTurn citation markers', () => {
  it('links a plain marker', () => {
    expect(renderAnswer('Sized for the 25-year storm. [C1]')).toContain(
      '<button class="inlineCitation">[C1]</button>',
    );
  });

  it('links a marker the model wrapped in backticks', () => {
    const html = renderAnswer('Sized for the 25-year storm. `[C1]`');
    expect(html).toContain('<button class="inlineCitation">[C1]</button>');
    expect(html).not.toContain('<code');
  });

  it('links several markers sharing one backticked span', () => {
    const html = renderAnswer('Sized for the 25-year storm. `[C1], [C2]`', [
      citation('C1'),
      citation('C2'),
    ]);
    expect(html).toContain('<button class="inlineCitation">[C1]</button>');
    expect(html).toContain('<button class="inlineCitation">[C2]</button>');
  });

  it('leaves real inline code alone', () => {
    const html = renderAnswer('Run `vera search manual.vera "detention"` first. [C1]');
    expect(html).toContain('<code>vera search manual.vera &quot;detention&quot;</code>');
  });

  it('renders an unretrieved id as text rather than a dead button', () => {
    const html = renderAnswer('Not retrieved this turn. `[C9]`');
    expect(html).not.toContain('inlineCitation');
    expect(html).toContain('[C9]');
  });

  it('keeps react-markdown internals out of the DOM', () => {
    expect(renderAnswer('- Sized for the 25-year storm. [C1]')).not.toContain('node=');
  });
});
