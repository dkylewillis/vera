import { Search } from 'lucide-react';
import { fileName, formatPages } from '../lib/formatting';
import type { SearchResult, SkippedSemanticModelGroup } from '../types';

export function CenterSearchView({
  submittedSearchQuery,
  results,
  selected,
  searchQuery,
  mode,
  topK,
  contextChunks,
  includeFigures,
  skippedSemanticModelGroups = [],
  selectedFilesCount,
  scopeLabel,
  hasSearchableScope,
  busy,
  searchBusy,
  onSelectResult,
  onSearchQueryChange,
  onSearch,
  onClearSelectedFiles,
  onModeChange,
  onTopKChange,
  onContextChunksChange,
  onIncludeFiguresChange,
}: {
  submittedSearchQuery: string;
  results: SearchResult[];
  selected: SearchResult | null;
  searchQuery: string;
  mode: string;
  topK: number;
  contextChunks: number;
  includeFigures: boolean;
  skippedSemanticModelGroups?: SkippedSemanticModelGroup[];
  selectedFilesCount: number;
  scopeLabel: string;
  hasSearchableScope: boolean;
  busy: boolean;
  searchBusy: boolean;
  onSelectResult: (result: SearchResult) => void;
  onSearchQueryChange: (value: string) => void;
  onSearch: () => void;
  onClearSelectedFiles: () => void;
  onModeChange: (value: string) => void;
  onTopKChange: (value: number) => void;
  onContextChunksChange: (value: number) => void;
  onIncludeFiguresChange: (value: boolean) => void;
}) {
  return (
    <section className={submittedSearchQuery ? 'centerSearch centerSearch--active' : 'centerSearch centerSearch--empty'}>
      {submittedSearchQuery ? (
        <div className="searchThread">
          <article className="chatMessage userMessage searchQueryMessage">
            <p>{submittedSearchQuery}</p>
          </article>
          <article className="chatMessage assistantMessage searchResponse">
            <span>{results.length} result{results.length === 1 ? '' : 's'}</span>
            {skippedSemanticModelGroups.length > 0 ? (
              <p className="searchSkippedWarning" role="status">
                Semantic search skipped {skippedSemanticModelGroups.length} model
                group{skippedSemanticModelGroups.length === 1 ? '' : 's'} because
                the embedder is unavailable. Keyword matches still appear. Check
                File → Settings → Python plugins if you expected semantic hits.
              </p>
            ) : null}
            {results.length > 0 ? (
              <div className="centerSearchResults">
                {results.map((result, index) => (
                  <button
                    className={selected?.chunk_id === result.chunk_id ? 'searchResultCard active' : 'searchResultCard'}
                    key={`${result.file || result.document_id}-${result.chunk_id}`}
                    onClick={() => onSelectResult(result)}
                  >
                    <span className="searchResultRank">{index + 1}</span>
                    <span className="searchResultBody">
                      <span className="resultRowMeta">{result.score.toFixed(3)} · p. {formatPages(result.page_start, result.page_end)}{result.file ? ` · ${fileName(result.file)}` : ''}</span>
                      <strong>{result.heading_path || result.source_filename || result.chunk_id}</strong>
                      <span className="resultRowText">{result.text}</span>
                    </span>
                  </button>
                ))}
              </div>
            ) : (
              <p className="searchNoResults">No matching passages found.</p>
            )}
          </article>
        </div>
      ) : (
        <div className="chatEmptyState">
          <Search size={26} />
          <p>Search your documents</p>
        </div>
      )}
      <div className="searchComposerWrap">
        <div className="composerScope searchComposerScope">
          <span>{scopeLabel}</span>
          {selectedFilesCount > 0 ? (
            <button type="button" onClick={onClearSelectedFiles}>Clear</button>
          ) : null}
        </div>
        <div className="searchComposer">
          <textarea
            value={searchQuery}
            rows={1}
            onChange={(event) => onSearchQueryChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                if (hasSearchableScope && searchQuery.trim() && !busy) onSearch();
              }
            }}
            placeholder="Search the active scope…"
            aria-label="Search query"
          />
          <button
            type="button"
            className="askSendButton"
            onClick={onSearch}
            disabled={!hasSearchableScope || !searchQuery.trim() || busy}
            aria-label="Search"
          >
            {searchBusy ? <span className="askSpinner" /> : <Search size={14} />}
          </button>
        </div>
        <div className="searchOptionsBar">
          <label>
            <span>Mode</span>
            <select value={mode} onChange={(event) => onModeChange(event.target.value)}>
              <option value="hybrid">Hybrid</option>
              <option value="semantic">Semantic</option>
              <option value="keyword">Keyword</option>
            </select>
          </label>
          <label>
            <span>Results</span>
            <input type="number" min={1} max={50} value={topK} onChange={(event) => onTopKChange(Number(event.target.value))} />
          </label>
          <label>
            <span>Context</span>
            <input type="number" min={0} max={5} value={contextChunks} onChange={(event) => onContextChunksChange(Number(event.target.value))} />
          </label>
          <label className="searchFiguresOption">
            <input type="checkbox" checked={includeFigures} onChange={(event) => onIncludeFiguresChange(event.target.checked)} />
            <span>Figures</span>
          </label>
        </div>
      </div>
    </section>
  );
}
