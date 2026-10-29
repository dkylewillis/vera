import { SIDECAR_ACTIONS } from '../../shared/protocol';
import type { LibraryIndexStatus, SearchReport, SearchResult, SkippedSemanticModelGroup } from '../types';

/** Escape glob metacharacters so a folder named `a[1]` only matches itself. */
function escapeGlob(value: string): string {
  return value.replace(/[[*?]/g, (char) => `[${char}]`);
}

/**
 * Root-relative include pattern for searching one subfolder of a library, or
 * null when the folder is not strictly inside it.
 */
export function folderScopeInclude(libraryPath: string, folderPath: string): string | null {
  const root = libraryPath.replace(/[\\/]+$/, '');
  if (!root || folderPath.length <= root.length + 1) return null;
  if (folderPath.slice(0, root.length).toLowerCase() !== root.toLowerCase()) return null;
  if (!/[\\/]/.test(folderPath[root.length])) return null;
  const relative = folderPath.slice(root.length + 1).replace(/\\/g, '/').replace(/\/+$/, '');
  return relative ? `${escapeGlob(relative)}/**` : null;
}

export function libraryQueryScope(
  activeLibraryPath: string,
  selectedFiles: string[],
  activeIndexStatus?: Pick<LibraryIndexStatus, 'fresh' | 'recursive' | 'excludes'> | null,
  folderScopePath = '',
): { recursive?: boolean; excludes?: string[]; includes?: string[] } {
  if (!activeLibraryPath || selectedFiles.length > 0) return {};
  const include = folderScopePath ? folderScopeInclude(activeLibraryPath, folderScopePath) : null;
  return {
    recursive: activeIndexStatus?.fresh ? activeIndexStatus.recursive ?? true : true,
    excludes: activeIndexStatus?.excludes ?? [],
    ...(include ? { includes: [include] } : {}),
  };
}

export function buildSearchPayload(options: {
  searchScopePath: string;
  selectedFiles: string[];
  activeLibraryPath: string;
  activeIndexStatus?: Pick<LibraryIndexStatus, 'fresh' | 'recursive' | 'excludes'> | null;
  folderScopePath?: string;
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
    ...libraryQueryScope(
      options.activeLibraryPath,
      options.selectedFiles,
      options.activeIndexStatus,
      options.folderScopePath,
    ),
    query: options.query,
    mode: options.mode,
    top_k: options.topK,
    context_chunks: options.contextChunks,
    include_regions: true,
    include_figures: options.includeFigures,
    include_figure_data: false,
  };
}

export function unwrapSearchReport(result: SearchReport | SearchResult[] | null | undefined): {
  results: SearchResult[];
  skippedSemanticModelGroups: SkippedSemanticModelGroup[];
} {
  if (Array.isArray(result)) {
    return { results: result, skippedSemanticModelGroups: [] };
  }
  if (!result || typeof result !== 'object') {
    return { results: [], skippedSemanticModelGroups: [] };
  }
  return {
    results: Array.isArray(result.results) ? result.results : [],
    skippedSemanticModelGroups: Array.isArray(result.skipped_semantic_model_groups)
      ? result.skipped_semantic_model_groups
      : [],
  };
}
