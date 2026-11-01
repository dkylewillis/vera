import { describe, expect, it } from 'vitest';
import {
  markdownDisplayLines,
  markdownNodeOverlaps,
  markdownRenderBlocks,
  overlappingRanges,
} from './MarkdownSourceViewer';

describe('overlappingRanges', () => {
  it('returns every pre-rendered block that covers a cited line', () => {
    const ranges = [
      { start: 1, end: 1 },
      { start: 3, end: 3 },
      { start: 5, end: 7 },
    ];
    expect(overlappingRanges(ranges, new Set([3, 6]))).toEqual([1, 2]);
    expect(overlappingRanges(ranges, new Set())).toEqual([]);
  });
});

describe('markdownDisplayLines', () => {
  it('strips a leading UTF-8 BOM so line numbers match ingest locators', () => {
    expect(markdownDisplayLines('\ufeff# Title\n\nBody')).toEqual(['# Title', '', 'Body']);
  });

  it('keeps ordinary Markdown unchanged', () => {
    expect(markdownDisplayLines('# Title\n\nBody')).toEqual(['# Title', '', 'Body']);
  });
});

describe('markdownRenderBlocks', () => {
  it('keeps a table together and leaves the surrounding prose as its own blocks', () => {
    const blocks = markdownRenderBlocks([
      '# Detention',
      '',
      'Ponds hold stormwater.',
      '',
      '| Item | Size |',
      '| --- | --- |',
      '| Pond | Large |',
      '',
      '- Check the outlet.',
    ].join('\n'));
    expect(blocks.map((block) => [block.start, block.end, block.source.split('\n')[0]])).toEqual([
      [1, 1, '# Detention'],
      [3, 3, 'Ponds hold stormwater.'],
      [5, 7, '| Item | Size |'],
      [9, 9, '- Check the outlet.'],
    ]);
  });

  it('matches a highlight to the Markdown node that covers those lines', () => {
    expect(markdownNodeOverlaps({ position: { start: { line: 5 }, end: { line: 7 } } }, new Set([6]))).toBe(true);
    expect(markdownNodeOverlaps({ position: { start: { line: 5 }, end: { line: 7 } } }, new Set([8]))).toBe(false);
  });

  it('keeps a fenced block intact', () => {
    const blocks = markdownRenderBlocks('Before\n\n```\n| not | a table |\n```\n');
    expect(blocks).toHaveLength(2);
    expect(blocks[1].source).toBe('```\n| not | a table |\n```');
    expect(blocks[1].start).toBe(3);
    expect(blocks[1].end).toBe(5);
  });
});
