import type { FigureResult, SearchResult } from '../types';

export function figureCacheKey(path: string, assetId: string): string {
  return `${path.replace(/\\/g, '/').toLowerCase()}\0${assetId}`;
}

export function sameSearchResult(left: SearchResult, right: SearchResult): boolean {
  return (
    left.chunk_id === right.chunk_id
    && (left.file || left.source_filename || '') === (right.file || right.source_filename || '')
  );
}

export function mergeFigureData(
  result: SearchResult,
  loadedFigures: FigureResult[],
): SearchResult {
  if (!result.figures?.length || !loadedFigures.length) return result;
  const loadedById = new Map(
    loadedFigures
      .filter((figure) => figure.asset_id)
      .map((figure) => [figure.asset_id as string, figure]),
  );
  return {
    ...result,
    figures: result.figures.map((figure) => {
      const loaded = figure.asset_id ? loadedById.get(figure.asset_id) : undefined;
      return loaded ? { ...figure, ...loaded } : figure;
    }),
  };
}
