import type { RegionResult } from '../types';

export interface SheetPreview {
  preview_row_limit?: number;
  preview_column_limit?: number;
  sheets: Array<{
    name: string;
    page?: number;
    row_count: number;
    column_count: number;
    rows: string[][];
  }>;
}

export interface SlidePreview {
  slides: Array<{
    slide: number;
    blocks: Array<{ block_id: string; kind: string; text: string }>;
  }>;
}

export interface CellRange {
  sheet?: string;
  startCol: number;
  startRow: number;
  endCol: number;
  endRow: number;
}

const CELL = /^([A-Za-z]+)(\d+)$/;

export function columnIndex(letters: string): number {
  let index = 0;
  for (const char of letters.toUpperCase()) {
    index = index * 26 + (char.charCodeAt(0) - 64);
  }
  return index;
}

export function parseA1Range(range: string): Omit<CellRange, 'sheet'> | null {
  const [start, end] = range.split(':');
  const startMatch = start ? CELL.exec(start) : null;
  const endMatch = end ? CELL.exec(end) : startMatch;
  if (!startMatch || !endMatch) return null;
  const startCol = columnIndex(startMatch[1]);
  const endCol = columnIndex(endMatch[1]);
  const startRow = Number(startMatch[2]);
  const endRow = Number(endMatch[2]);
  if (!startCol || !endCol || !startRow || !endRow) return null;
  return {
    startCol: Math.min(startCol, endCol),
    endCol: Math.max(startCol, endCol),
    startRow: Math.min(startRow, endRow),
    endRow: Math.max(startRow, endRow),
  };
}

export function citedSheetRanges(regions: RegionResult[]): CellRange[] {
  const ranges: CellRange[] = [];
  for (const region of regions) {
    if (region.kind !== 'sheet_range' || !region.range) continue;
    const parsed = parseA1Range(region.range);
    if (!parsed) continue;
    ranges.push({ sheet: region.sheet, ...parsed });
  }
  return ranges;
}

export function cellInRanges(row: number, column: number, ranges: CellRange[]): boolean {
  return ranges.some((range) => (
    row >= range.startRow
    && row <= range.endRow
    && column >= range.startCol
    && column <= range.endCol
  ));
}

export function rangeStartsBeyondPreview(ranges: CellRange[], previewRowCount: number): boolean {
  return ranges.some((range) => range.startRow > previewRowCount);
}

export function citedSlides(regions: RegionResult[]): Set<number> {
  const slides = new Set<number>();
  for (const region of regions) {
    if (region.kind === 'slide' && typeof region.slide === 'number') slides.add(region.slide);
  }
  return slides;
}

export function citedBlockIds(regions: RegionResult[]): Set<string> {
  const ids = new Set<string>();
  for (const region of regions) {
    if (region.block_id) ids.add(region.block_id);
  }
  return ids;
}
