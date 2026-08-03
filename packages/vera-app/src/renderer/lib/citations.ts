import type { ChatCitationResult } from '../types';

const CITATION_MARKER = /\[(C\d+)\]/g;

export function citationsForTurn(
  turnCitations: Iterable<ChatCitationResult>,
  sessionCitations: Iterable<ChatCitationResult>,
): ChatCitationResult[] {
  const citationsById = new Map(
    Array.from(sessionCitations, (citation) => [citation.id, citation]),
  );
  // A turn's own payload is authoritative. This preserves reused citations while
  // preventing a legacy/session-wide duplicate ID from redirecting its buttons.
  for (const citation of turnCitations) {
    citationsById.set(citation.id, citation);
  }
  return [...citationsById.values()];
}

export function firstCitationInAnswer(
  answer: string,
  citations: Iterable<ChatCitationResult>,
): ChatCitationResult | null {
  const citationsById = new Map(
    Array.from(citations, (citation) => [citation.id, citation]),
  );

  for (const match of answer.matchAll(CITATION_MARKER)) {
    const citation = citationsById.get(match[1]);
    if (citation) return citation;
  }
  return null;
}
