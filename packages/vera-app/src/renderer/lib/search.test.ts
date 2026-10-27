import { describe, expect, it } from 'vitest';
import { SIDECAR_ACTIONS } from '../../shared/protocol';
import { buildSearchPayload, folderScopeInclude, libraryQueryScope, unwrapSearchReport } from './search';

describe('libraryQueryScope', () => {
  it('omits recursive options when files are selected or no library is active', () => {
    expect(libraryQueryScope('', [], { fresh: true, recursive: false, excludes: ['tmp'] })).toEqual({});
    expect(libraryQueryScope('C:\\lib', ['a.vera'], { fresh: true, recursive: false, excludes: ['tmp'] })).toEqual({});
  });

  it('uses a fresh index recursive flag and otherwise defaults to recursive', () => {
    expect(libraryQueryScope('C:\\lib', [], { fresh: true, recursive: false, excludes: ['tmp'] })).toEqual({
      recursive: false,
      excludes: ['tmp'],
    });
    expect(libraryQueryScope('C:\\lib', [], { fresh: false, recursive: false, excludes: ['tmp'] })).toEqual({
      recursive: true,
      excludes: ['tmp'],
    });
    expect(libraryQueryScope('C:\\lib', [])).toEqual({
      recursive: true,
      excludes: [],
    });
  });

  it('limits a library search to one subfolder with an include pattern', () => {
    expect(libraryQueryScope('C:\\lib', [], null, 'C:\\lib\\projects\\smith')).toEqual({
      recursive: true,
      excludes: [],
      includes: ['projects/smith/**'],
    });
    expect(libraryQueryScope('C:\\lib', ['C:\\lib\\a.vera'], null, 'C:\\lib\\projects')).toEqual({});
    expect(libraryQueryScope('C:\\lib', [], null, 'C:\\other\\projects')).not.toHaveProperty('includes');
  });
});

describe('folderScopeInclude', () => {
  it('builds a root-relative pattern only for folders strictly inside the library', () => {
    expect(folderScopeInclude('C:\\lib', 'C:\\lib\\a\\b')).toBe('a/b/**');
    expect(folderScopeInclude('/home/me/lib/', '/home/me/lib/a')).toBe('a/**');
    expect(folderScopeInclude('C:\\lib', 'c:\\LIB\\a')).toBe('a/**');
    expect(folderScopeInclude('C:\\lib', 'C:\\lib')).toBeNull();
    expect(folderScopeInclude('C:\\lib', 'C:\\library\\a')).toBeNull();
    expect(folderScopeInclude('C:\\lib', '')).toBeNull();
  });

  it('escapes glob characters in folder names', () => {
    expect(folderScopeInclude('C:\\lib', 'C:\\lib\\Phase [1]')).toBe('Phase [[]1]/**');
    expect(folderScopeInclude('C:\\lib', 'C:\\lib\\what?*')).toBe('what[?][*]/**');
  });
});

describe('buildSearchPayload', () => {
  it('builds a sidecar search call with regions and lazy figures', () => {
    expect(buildSearchPayload({
      searchScopePath: 'C:\\lib',
      selectedFiles: ['C:\\lib\\a.vera'],
      activeLibraryPath: 'C:\\lib',
      activeIndexStatus: { fresh: true, recursive: false, excludes: ['tmp'] },
      query: 'detention',
      mode: 'hybrid',
      topK: 8,
      contextChunks: 1,
      includeFigures: true,
    })).toEqual({
      action: SIDECAR_ACTIONS.search,
      path: 'C:\\lib',
      paths: ['C:\\lib\\a.vera'],
      query: 'detention',
      mode: 'hybrid',
      top_k: 8,
      context_chunks: 1,
      include_regions: true,
      include_figures: true,
      include_figure_data: false,
    });
  });
});

describe('unwrapSearchReport', () => {
  it('reads results and skipped semantic groups from the sidecar report', () => {
    const first = {
      chunk_id: 'chunk-1',
      score: 1,
      text: 'hit',
      page_start: 1,
      page_end: 1,
      heading_path: null,
      source_filename: 'manual.pdf',
      document_id: 'document-1',
    };
    expect(unwrapSearchReport({
      results: [first],
      skipped_semantic_model_groups: [
        { model_name: 'openai:text-embedding-3-small', dimension: 1536, error: 'missing key' },
      ],
    })).toEqual({
      results: [first],
      skippedSemanticModelGroups: [
        { model_name: 'openai:text-embedding-3-small', dimension: 1536, error: 'missing key' },
      ],
    });
  });

  it('accepts a legacy list payload', () => {
    expect(unwrapSearchReport([])).toEqual({ results: [], skippedSemanticModelGroups: [] });
  });
});
