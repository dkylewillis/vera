import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { CenterSearchView } from './CenterSearchView';

describe('CenterSearchView', () => {
  it('renders the empty-state prompt before a query is submitted', () => {
    const html = renderToStaticMarkup(
      <CenterSearchView
        submittedSearchQuery=""
        results={[]}
        selected={null}
        searchQuery=""
        mode="hybrid"
        topK={10}
        contextChunks={0}
        includeFigures={false}
        skippedSemanticModelGroups={[]}
        selectedFilesCount={0}
        scopeLabel="No search scope"
        hasSearchableScope={false}
        busy={false}
        searchBusy={false}
        onSelectResult={() => {}}
        onSearchQueryChange={() => {}}
        onSearch={() => {}}
        onClearSelectedFiles={() => {}}
        onModeChange={() => {}}
        onTopKChange={() => {}}
        onContextChunksChange={() => {}}
        onIncludeFiguresChange={() => {}}
      />,
    );
    expect(html).toContain('Search your documents');
    expect(html).toContain('centerSearch--empty');
  });
});
