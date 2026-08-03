import { describe, expect, it } from 'vitest';

import type { ChatCitationResult } from '../types';
import { citationsForTurn, firstCitationInAnswer } from './citations';

function citation(id: string, chunkId = `chunk_${id}`): ChatCitationResult {
  return {
    id,
    label: `[${id}]`,
    result: {
      chunk_id: chunkId,
      score: 0.9,
      text: `Passage ${id}`,
      page_start: Number(id.slice(1)),
      page_end: Number(id.slice(1)),
      heading_path: '',
      source_filename: 'manual.pdf',
      document_id: 'document_0001',
    },
  };
}

describe('firstCitationInAnswer', () => {
  it('uses answer order instead of retrieval order', () => {
    const citations = [citation('C1'), citation('C2'), citation('C3')];

    expect(firstCitationInAnswer('Start here [C3], then compare [C1].', citations)?.id).toBe('C3');
  });

  it('skips unknown markers and finds the first linkable citation', () => {
    const citations = [citation('C2')];

    expect(firstCitationInAnswer('Unsupported [C9], supported [C2].', citations)?.id).toBe('C2');
  });

  it('returns null when the answer has no linkable citation', () => {
    expect(firstCitationInAnswer('No cited claims.', [citation('C1')])).toBeNull();
  });
});

describe('citationsForTurn', () => {
  it('prefers the turn payload when a session citation reuses its id', () => {
    const legacyCitation = citation('C1', 'old_chunk');
    const turnCitation = citation('C1', 'current_chunk');

    expect(citationsForTurn([turnCitation], [legacyCitation])[0].result.chunk_id).toBe('current_chunk');
  });

  it('keeps an earlier citation available when the turn reuses its marker', () => {
    const earlierCitation = citation('C1', 'earlier_chunk');

    expect(citationsForTurn([], [earlierCitation])[0]).toBe(earlierCitation);
  });
});
