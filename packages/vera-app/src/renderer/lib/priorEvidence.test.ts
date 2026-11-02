import { describe, expect, it } from 'vitest';

import type { ChatCitationResult, SessionTurn } from '../types';
import { citationKey, priorCitationRefs, priorEvidence } from './priorEvidence';

function citation(id: string, chunkId: string, file?: string): ChatCitationResult {
  return {
    id,
    label: `[${id}] p. 1`,
    result: {
      chunk_id: chunkId,
      score: 1,
      text: `text ${id}`,
      page_start: 1,
      page_end: 1,
      heading_path: 'Scope',
      source_filename: 'manual.pdf',
      document_id: 'document_0001',
      ...(file ? { file } : {}),
    },
  };
}

describe('prior evidence', () => {
  it('keys citations by file and chunk id', () => {
    expect(citationKey(citation('C1', 'chunk_0001'))).toBe('chunk_0001');
    expect(citationKey(citation('C1', 'chunk_0001', 'C:\\a.vera'))).toBe('C:\\a.vera::chunk_0001');
  });

  it('keeps the first id for a chunk and separates files', () => {
    const turns: SessionTurn[] = [
      {
        role: 'assistant',
        content: 'a',
        timestamp: 1,
        citations: [citation('C1', 'chunk_0001', 'C:\\a.vera')],
      },
      {
        role: 'assistant',
        content: 'b',
        timestamp: 2,
        citations: [
          citation('C9', 'chunk_0001', 'C:\\a.vera'),
          citation('C2', 'chunk_0001', 'C:\\b.vera'),
        ],
      },
    ];
    expect(priorCitationRefs(turns)).toEqual([
      { id: 'C1', chunk_id: 'chunk_0001', file: 'C:\\a.vera' },
      { id: 'C2', chunk_id: 'chunk_0001', file: 'C:\\b.vera' },
    ]);
  });

  it('lists newest evidence first and flags the latest turn', () => {
    const turns: SessionTurn[] = [
      { role: 'user', content: 'q', timestamp: 1 },
      { role: 'assistant', content: 'a', timestamp: 2, citations: [citation('C1', 'chunk_0001')] },
      { role: 'assistant', content: 'b', timestamp: 3, citations: [citation('C2', 'chunk_0002')] },
    ];
    const evidence = priorEvidence(turns);
    expect(evidence.map((item) => item.id)).toEqual(['C2', 'C1']);
    expect(evidence[0]?.from_latest).toBe(true);
    expect(evidence[1]?.from_latest).toBe(false);
  });
});
