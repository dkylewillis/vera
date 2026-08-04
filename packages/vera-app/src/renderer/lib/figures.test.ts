import { describe, expect, it } from 'vitest';
import type { SearchResult } from '../types';
import { figureCacheKey, mergeFigureData, sameSearchResult } from './figures';

const result: SearchResult = {
  chunk_id: 'chunk-1',
  score: 1,
  text: 'Evidence',
  page_start: 1,
  page_end: 1,
  heading_path: null,
  source_filename: 'manual.pdf',
  document_id: 'document-1',
  file: 'C:\\Library\\manual.vera',
  figures: [
    {
      asset_id: 'image-1',
      page_number: 1,
      caption: 'A figure',
      included_in_context: true,
    },
  ],
};

describe('lazy figure data', () => {
  it('merges image data without losing search metadata', () => {
    const merged = mergeFigureData(result, [{
      asset_id: 'image-1',
      page_number: 1,
      data_url: 'data:image/png;base64,abc',
    }]);

    expect(merged.figures?.[0]).toMatchObject({
      asset_id: 'image-1',
      caption: 'A figure',
      included_in_context: true,
      data_url: 'data:image/png;base64,abc',
    });
  });

  it('uses stable archive and result identities', () => {
    expect(figureCacheKey('C:\\Library\\manual.vera', 'image-1')).toBe(
      figureCacheKey('c:/library/manual.vera', 'image-1'),
    );
    expect(sameSearchResult(result, { ...result })).toBe(true);
    expect(sameSearchResult(result, { ...result, chunk_id: 'chunk-2' })).toBe(false);
  });
});
