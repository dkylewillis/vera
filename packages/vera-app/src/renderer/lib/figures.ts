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

export function hydrateFiguresFromCache(
  result: SearchResult,
  resultPath: string,
  cache: Map<string, FigureResult>,
): { hydrated: SearchResult; missingAssetIds: string[] } {
  const cachedFigures: FigureResult[] = [];
  for (const figure of result.figures || []) {
    if (!figure.asset_id) continue;
    if (figure.data_url) {
      cache.set(figureCacheKey(resultPath, figure.asset_id), figure);
      cachedFigures.push(figure);
      continue;
    }
    const cached = cache.get(figureCacheKey(resultPath, figure.asset_id));
    if (cached) cachedFigures.push(cached);
  }
  const hydrated = mergeFigureData(result, cachedFigures);
  const missingAssetIds = (hydrated.figures || [])
    .filter((figure) => figure.asset_id && !figure.data_url)
    .map((figure) => figure.asset_id as string);
  return { hydrated, missingAssetIds };
}
