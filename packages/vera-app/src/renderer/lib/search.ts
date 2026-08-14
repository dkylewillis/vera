import { SIDECAR_ACTIONS } from '../../shared/protocol';
import type { LibraryIndexStatus } from '../types';

export function libraryQueryScope(
  activeLibraryPath: string,
  selectedFiles: string[],
  activeIndexStatus?: Pick<LibraryIndexStatus, 'fresh' | 'recursive' | 'excludes'> | null,
): { recursive?: boolean; excludes?: string[] } {
  if (!activeLibraryPath || selectedFiles.length > 0) return {};
  return {
    recursive: activeIndexStatus?.fresh ? activeIndexStatus.recursive ?? true : true,
    excludes: activeIndexStatus?.excludes ?? [],
  };
}

export function buildSearchPayload(options: {
  searchScopePath: string;
  selectedFiles: string[];
  activeLibraryPath: string;
  activeIndexStatus?: Pick<LibraryIndexStatus, 'fresh' | 'recursive' | 'excludes'> | null;
  query: string;
  mode: string;
  topK: number;
  contextChunks: number;
  includeFigures: boolean;
}): Record<string, unknown> {
  return {
    action: SIDECAR_ACTIONS.search,
    path: options.searchScopePath,
    ...(options.selectedFiles.length ? { paths: options.selectedFiles } : {}),
    ...libraryQueryScope(options.activeLibraryPath, options.selectedFiles, options.activeIndexStatus),
    query: options.query,
    mode: options.mode,
    top_k: options.topK,
    context_chunks: options.contextChunks,
    include_regions: true,
    include_figures: options.includeFigures,
    include_figure_data: false,
  };
}
