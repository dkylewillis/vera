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
function renderAnswer(
  content: string,
  citations: ChatCitationResult[] = [citation('C1')],
  linkableCitations?: ChatCitationResult[],
) {
  const turn: SessionTurn = { role: 'assistant', content, citations, timestamp: 0 };
  const html = renderToStaticMarkup(
    <ChatTurn
      turn={turn}
      linkableCitations={linkableCitations}
      selectCitation={() => {}}
      showTrace={false}
    />,
  );
  return html.slice(html.indexOf('<div class="markdownBody">'));
}

describe('ChatTurn citation markers', () => {
  it('links a plain marker', () => {
    expect(renderAnswer('Sized for the 25-year storm. [C1]')).toContain(
      '<button class="inlineCitation">[C1]</button>',
    );
  });

  it('links a marker reused from an earlier turn without a new search', () => {
    expect(renderAnswer('The earlier result still applies. [C1]', [], [citation('C1')])).toContain(
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

describe('ChatTurn LaTeX', () => {
  it('renders inline math as KaTeX beside a citation', () => {
    const html = renderAnswer('The lift coefficient is $C_L$. [C1]');
    expect(html).toContain('class="katex"');
    expect(html).toContain('<button class="inlineCitation">[C1]</button>');
  });

  it('renders display math as KaTeX', () => {
    const html = renderAnswer('$$E = mc^2$$\n\nSee [C1].');
    expect(html).toContain('katex-display');
  });

  it('renders TeX-style delimiters', () => {
    const html = renderAnswer('Inline \\(a^2\\) and display \\[Q = CiA\\]. [C1]');
    expect(html).toContain('class="katex"');
    expect(html).toContain('katex-display');
  });

  it('renders math when the turn has no citations', () => {
    const html = renderAnswer('Use $Q = CiA$.', []);
    expect(html).toContain('class="katex"');
  });

  it('renders inline math that starts with a digit', () => {
    const html = renderAnswer('Peak flow is $2.1Q$.', []);
    expect(html).toContain('class="katex"');
  });

  it('leaves paired currency amounts as text', () => {
    const html = renderAnswer('Budget is $20,000 and $30,000. [C1]');
    expect(html).not.toContain('class="katex"');
    expect(html).toContain('$20,000');
  });

  it('leaves math inside fenced code as code', () => {
    const html = renderAnswer('```\n$C_L$\n```\n\n[C1]');
    expect(html).toContain('<code>');
    expect(html).not.toContain('class="katex"');
  });

  it('does not throw on incomplete display math', () => {
    expect(() => renderAnswer('$$E = mc', [])).not.toThrow();
  });
});
