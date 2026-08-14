import type { SessionTurn, StreamEvent } from '../types';

export function traceKey(sessionId: string, timestamp: number): string {
  return `${sessionId}:${timestamp}`;
}

export function stripTrace(turn: SessionTurn): SessionTurn {
  if (!turn.trace) return turn;
  const { trace: _trace, ...rest } = turn;
  return rest;
}

export function hydrateSessionTurns(
  turns: SessionTurn[],
  traces: Map<string, StreamEvent[]>,
  sessionId: string,
): SessionTurn[] {
  return turns.map((turn) => {
    if (turn.role !== 'assistant') return turn;
    const trace = traces.get(traceKey(sessionId, turn.timestamp));
    return trace ? { ...turn, trace } : turn;
  });
}
