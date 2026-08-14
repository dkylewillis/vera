import { describe, expect, it } from 'vitest';
import type { SessionTurn } from '../types';
import { hydrateSessionTurns, stripTrace, traceKey } from './sessions';

describe('session traces', () => {
  it('keys traces by session and turn timestamp', () => {
    expect(traceKey('sess_1', 42)).toBe('sess_1:42');
  });

  it('strips traces before persistence and rehydrates them from memory', () => {
    const turn: SessionTurn = {
      role: 'assistant',
      content: 'Answer',
      timestamp: 42,
      trace: [{ id: 't1', event: 'llm_request' }],
    };
    expect(stripTrace(turn)).toEqual({
      role: 'assistant',
      content: 'Answer',
      timestamp: 42,
    });
    const traces = new Map([[traceKey('sess_1', 42), turn.trace ?? []]]);
    expect(hydrateSessionTurns([turn], traces, 'sess_1')[0].trace).toEqual(turn.trace);
    expect(hydrateSessionTurns([{ ...turn, role: 'user', trace: undefined }], traces, 'sess_1')[0].trace).toBeUndefined();
  });
});
