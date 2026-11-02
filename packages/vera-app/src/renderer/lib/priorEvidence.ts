import type { ChatCitationResult, SessionTurn } from '../types';

/** Stable key for a cited chunk. Includes the archive path when the turn stored one. */
export function citationKey(citation: ChatCitationResult): string {
  const chunkId = citation.result?.chunk_id;
  if (!chunkId) return '';
  const file = citation.result?.file;
  return file ? `${file}::${chunkId}` : chunkId;
}

export interface PriorCitationRef {
  id: string;
  chunk_id: string;
  file?: string;
}

export interface PriorEvidenceItem {
  id: string;
  file?: string;
  chunk_id: string;
  text: string;
  page_start: number | null;
  page_end: number | null;
  heading_path: string | null;
  source_filename: string | null;
  from_latest: boolean;
}

/** Citation ids already used in this session, keyed so two files cannot share a chunk id. */
export function priorCitationRefs(turns: SessionTurn[]): PriorCitationRef[] {
  const byKey = new Map<string, PriorCitationRef>();
  for (const turn of turns) {
    if (turn.role !== 'assistant' || !turn.citations) continue;
    for (const citation of turn.citations) {
      const key = citationKey(citation);
      const chunkId = citation.result?.chunk_id;
      if (!key || !chunkId || byKey.has(key)) continue;
      const file = citation.result?.file;
      byKey.set(key, file ? { id: citation.id, chunk_id: chunkId, file } : { id: citation.id, chunk_id: chunkId });
    }
  }
  return [...byKey.values()];
}

/**
 * Passages cited in earlier turns, newest first.
 * Citations from the latest assistant turn are flagged so the sidecar can keep them ahead of older ones.
 */
export function priorEvidence(turns: SessionTurn[]): PriorEvidenceItem[] {
  const latest = [...turns].reverse().find((turn) => turn.role === 'assistant' && turn.citations?.length);
  const seen = new Set<string>();
  const items: PriorEvidenceItem[] = [];
  for (const turn of [...turns].reverse()) {
    if (turn.role !== 'assistant' || !turn.citations) continue;
    for (const citation of turn.citations) {
      const key = citationKey(citation);
      const chunkId = citation.result?.chunk_id;
      if (!key || !chunkId || seen.has(key)) continue;
      seen.add(key);
      items.push({
        id: citation.id,
        ...(citation.result.file ? { file: citation.result.file } : {}),
        chunk_id: chunkId,
        text: citation.result.text ?? '',
        page_start: citation.result.page_start ?? null,
        page_end: citation.result.page_end ?? null,
        heading_path: citation.result.heading_path ?? null,
        source_filename: citation.result.source_filename ?? null,
        from_latest: turn === latest,
      });
    }
  }
  return items;
}
