import { describe, expect, it } from 'vitest';

import {
  cellInRanges,
  citedSlides,
  parseA1Range,
  rangeStartsBeyondPreview,
} from './officePreview';

describe('office preview highlights', () => {
  it('parses a sheet range and marks cells inside it', () => {
    const range = parseA1Range('B4:D18');
    expect(range).toEqual({ startCol: 2, startRow: 4, endCol: 4, endRow: 18 });
    expect(cellInRanges(4, 2, [{ ...range!, sheet: 'Budget' }])).toBe(true);
    expect(cellInRanges(3, 2, [{ ...range!, sheet: 'Budget' }])).toBe(false);
    expect(rangeStartsBeyondPreview([{ ...range!, sheet: 'Budget' }], 3)).toBe(true);
    expect(rangeStartsBeyondPreview([{ ...range!, sheet: 'Budget' }], 10)).toBe(false);
  });

  it('collects cited slide numbers', () => {
    expect(citedSlides([
      { kind: 'slide', slide: 7, block_id: 'block_000001' },
      { kind: 'text_span', start: { line: 1 } },
    ])).toEqual(new Set([7]));
  });
});
