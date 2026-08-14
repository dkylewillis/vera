import { useRef, type Dispatch, type SetStateAction } from 'react';
import type { CenterView } from '../components/AppShell';
import type { SidecarCall } from './useSidecarCall';
import { figureCacheKey, hydrateFiguresFromCache, mergeFigureData, sameSearchResult } from '../lib/figures';
import { buildSearchPayload } from '../lib/search';
import { SIDECAR_ACTIONS } from '../../shared/protocol';
import type {
  ChatCitationResult,
  FigureResult,
  LibraryIndexStatus,
  SearchResult,
  SourceDocumentResult,
} from '../types';

export type SearchHost = {
  hasSearchableScope: boolean;
  searchScopePath: string;
  selectedFiles: string[];
  activeLibraryPath: string;
  activeIndexStatus?: LibraryIndexStatus;
  searchQuery: string;
  mode: string;
  topK: number;
  contextChunks: number;
  includeFigures: boolean;
  path: string;
  sourceDocument: SourceDocumentResult | null;
  sourceDocumentPath: string;
  results: SearchResult[];
  call: SidecarCall;
  cancelActionScope: (scope: string) => void;
  promptForIndexBeforeQuery: () => Promise<boolean>;
  loadSourceDocument: (targetPath?: string, activateViewer?: boolean, requestId?: number) => Promise<void>;
  nextSourceLoadId: () => number;
  setErrorMessage: (message: string | null) => void;
  setSubmittedSearchQuery: Dispatch<SetStateAction<string>>;
  setResults: Dispatch<SetStateAction<SearchResult[]>>;
  setSelected: Dispatch<SetStateAction<SearchResult | null>>;
  setCenterView: Dispatch<SetStateAction<CenterView>>;
  setCitationJumpVersion: Dispatch<SetStateAction<number>>;
  setViewerMode: Dispatch<SetStateAction<'selection' | 'document' | 'info'>>;
  setPendingSourcePath: Dispatch<SetStateAction<string>>;
};

export type SearchController = ReturnType<typeof createSearchController>;

export function createSearchController(getHost: () => SearchHost) {
  const figureDataCache = new Map<string, FigureResult>();
  const figureDataLoadRef = { current: 0 };

  function selectSearchResult(result: SearchResult) {
    const host = getHost();
    const resultPath = result.file || host.path;
    const figureRequestId = ++figureDataLoadRef.current;
    const { hydrated, missingAssetIds } = hydrateFiguresFromCache(
      result,
      resultPath,
      figureDataCache,
    );
    host.setSelected(hydrated);
    if (resultPath && missingAssetIds.length) {
      void window.vera.request<FigureResult[]>({
        action: SIDECAR_ACTIONS.figureData,
        path: resultPath,
        asset_ids: missingAssetIds,
      }).then((response) => {
        if (!response.ok || figureRequestId !== figureDataLoadRef.current) return;
        const loadedFigures = response.result || [];
        for (const figure of loadedFigures) {
          if (!figure.asset_id || !figure.data_url) continue;
          figureDataCache.set(
            figureCacheKey(resultPath, figure.asset_id),
            figure,
          );
        }
        host.setSelected((current) => (
          current && sameSearchResult(current, result)
            ? mergeFigureData(current, loadedFigures)
            : current
        ));
        host.setResults((current) => current.map((entry) => (
          sameSearchResult(entry, result)
            ? mergeFigureData(entry, loadedFigures)
            : entry
        )));
      }).catch(() => undefined);
    }
    const requestId = host.nextSourceLoadId();
    if (resultPath && (resultPath !== host.sourceDocumentPath || !host.sourceDocument)) {
      void host.loadSourceDocument(resultPath, false, requestId);
    } else {
      host.cancelActionScope('source');
      host.setPendingSourcePath('');
    }
  }

  function selectChunkResult(index: number) {
    const host = getHost();
    const result = host.results[index];
    if (!result) return;
    selectSearchResult(result);
    host.setCitationJumpVersion((version) => version + 1);
  }

  function selectCitation(citation: ChatCitationResult, citationGroup?: ChatCitationResult[]) {
    const host = getHost();
    if (citationGroup?.length) {
      host.setResults(citationGroup.map((entry) => entry.result));
    }
    selectSearchResult(citation.result);
    host.setCitationJumpVersion((version) => version + 1);
    host.setViewerMode('document');
  }

  async function searchTarget() {
    const host = getHost();
    if (!host.hasSearchableScope) {
      host.setErrorMessage('This library does not contain any VERA documents yet.');
      return;
    }
    if (await host.promptForIndexBeforeQuery()) return;
    const result = await host.call<SearchResult[]>(
      buildSearchPayload({
        searchScopePath: host.searchScopePath,
        selectedFiles: host.selectedFiles,
        activeLibraryPath: host.activeLibraryPath,
        activeIndexStatus: host.activeIndexStatus,
        query: host.searchQuery,
        mode: host.mode,
        topK: host.topK,
        contextChunks: host.contextChunks,
        includeFigures: host.includeFigures,
      }),
      'Searching',
    );
    if (result) {
      host.setSubmittedSearchQuery(host.searchQuery.trim());
      host.setResults(result);
      if (result[0]) {
        selectSearchResult(result[0]);
      } else {
        host.setSelected(null);
      }
      host.setCenterView('search');
    }
  }

  return {
    searchTarget,
    selectSearchResult,
    selectChunkResult,
    selectCitation,
  };
}

export function useSearch(host: SearchHost): SearchController {
  const hostRef = useRef(host);
  hostRef.current = host;
  const controllerRef = useRef<SearchController | null>(null);
  if (!controllerRef.current) {
    controllerRef.current = createSearchController(() => hostRef.current);
  }
  return controllerRef.current;
}
