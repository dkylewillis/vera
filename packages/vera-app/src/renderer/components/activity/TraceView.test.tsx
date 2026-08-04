import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import type { StreamEvent } from '../../types';
import { TraceView } from './TraceView';

describe('TraceView', () => {
  it('renders only explicit search events as searches', () => {
    const events: StreamEvent[] = [
      { id: 'answer-1', event: 'search_start', query: 'front setbacks' },
      { id: 'answer-1', event: 'answer_delta', text: 'I will search.' },
      { id: 'answer-1', event: 'answer_delta', text: 'More streamed text.' },
      { id: 'answer-1', event: 'answer_reset' },
      {
        id: 'answer-1',
        event: 'search_done',
        query: 'front setbacks',
        mode: 'hybrid',
        hits: 4,
      },
    ];

    const html = renderToStaticMarkup(<TraceView events={events} />);

    expect(html.match(/>searching</g)).toHaveLength(1);
    expect(html.match(/>search done</g)).toHaveLength(1);
    expect(html).not.toContain('I will search.');
    expect(html).not.toContain('More streamed text.');
  });
});
