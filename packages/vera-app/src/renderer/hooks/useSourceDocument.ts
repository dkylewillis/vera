import { useRef, type Dispatch, type SetStateAction } from 'react';
import type { SidecarCall } from './useSidecarCall';
import type { ExplorerSelection } from '../lib/formatting';
import { SIDECAR_ACTIONS } from '../../shared/protocol';
import type { FolderEntry, SearchResult, SourceDocumentResult, WorkspaceFolderResult } from '../types';

export type ViewerMode = 'selection' | 'document' | 'info';

export type SourceDocumentHost = {
  path: string;
  folders: WorkspaceFolderResult[];
  pendingSourcePath: string;
  sourceDocument: SourceDocumentResult | null;
  sourceDocumentPath: string;
  call: SidecarCall;
  cancelActionScope: (scope: string) => void;
  openTargetPath: (value: string, options?: { asLibrary?: boolean; preserveLibrary?: boolean }) => Promise<void>;
  applyConvertDefaultsFromSelection: (selection?: ExplorerSelection | null) => void;
  setPendingSourcePath: Dispatch<SetStateAction<string>>;
  setLibraryInfoPath: Dispatch<SetStateAction<string>>;
  setSourceDocument: Dispatch<SetStateAction<SourceDocumentResult | null>>;
  setSourceDocumentPath: Dispatch<SetStateAction<string>>;
  setViewerMode: Dispatch<SetStateAction<ViewerMode>>;
  setViewerCollapsed: Dispatch<SetStateAction<boolean>>;
  setExplorerSelection: Dispatch<SetStateAction<ExplorerSelection | null>>;
  setSelected: Dispatch<SetStateAction<SearchResult | null>>;
};

export type SourceDocumentController = ReturnType<typeof createSourceDocumentController>;

export function createSourceDocumentController(getHost: () => SourceDocumentHost) {
  const sourceDocumentLoadRef = { current: 0 };

  function nextLoadId() {
    return ++sourceDocumentLoadRef.current;
  }

  function invalidateLoad() {
    sourceDocumentLoadRef.current += 1;
  }

  async function loadSourceDocument(
    targetPath = getHost().path,
    activateViewer = true,
    requestId = nextLoadId(),
  ) {
    const host = getHost();
    if (host.folders.some((folder) => folder.path === targetPath)) {
      if (requestId === sourceDocumentLoadRef.current) {
        host.setPendingSourcePath('');
      }
      return;
    }
    host.setPendingSourcePath(targetPath);
    try {
      const result = await host.call<SourceDocumentResult>(
        { action: SIDECAR_ACTIONS.source, path: targetPath },
        'Loading source',
        undefined,
        { scope: 'source' },
      );
      if (result && requestId === sourceDocumentLoadRef.current) {
        host.setLibraryInfoPath('');
        host.setSourceDocument(result);
        host.setSourceDocumentPath(targetPath);
        if (activateViewer) host.setViewerMode('document');
      }
    } finally {
      if (requestId === sourceDocumentLoadRef.current) {
        host.setPendingSourcePath('');
      }
    }
  }

  function closeSourceDocument() {
    const host = getHost();
    host.cancelActionScope('source');
    sourceDocumentLoadRef.current += 1;
    host.setSourceDocument(null);
    host.setSourceDocumentPath('');
    host.setPendingSourcePath('');
    host.setLibraryInfoPath('');
    host.setSelected(null);
    host.setViewerMode('document');
  }

  async function previewSourceDocument(
    entry: FolderEntry,
    options: { preserveLibrary?: boolean; replacePending?: boolean; mode?: 'document' | 'info' } = {},
  ) {
    if (entry.type !== 'vera' && entry.type !== 'pdf' && entry.type !== 'md' && entry.type !== 'docx' && entry.type !== 'pptx' && entry.type !== 'xlsx') return;
    const host = getHost();
    if (host.pendingSourcePath && !options.replacePending) return;
    if (options.replacePending) host.cancelActionScope('source');
    const selection: ExplorerSelection = { kind: 'file', path: entry.path, type: entry.type };
    const requestId = ++sourceDocumentLoadRef.current;
    host.setPendingSourcePath(entry.path);
    host.setLibraryInfoPath('');
    host.setSourceDocument(null);
    host.setSourceDocumentPath('');
    host.setExplorerSelection(selection);
    host.setSelected(null);
    host.setViewerMode(options.mode === 'info' ? 'info' : 'document');
    host.setViewerCollapsed(false);
    if (entry.type !== 'vera') {
      host.applyConvertDefaultsFromSelection(selection);
    }
    if (requestId !== sourceDocumentLoadRef.current) return;
    // Issue the preview before archive inspect. The sidecar handles one request
    // at a time, and inspect was delaying the first paint of the document.
    const loading = loadSourceDocument(entry.path, true, requestId);
    if (entry.type === 'vera') {
      const opening = host.openTargetPath(entry.path, { preserveLibrary: options.preserveLibrary ?? true });
      if (options.mode === 'info') {
        await Promise.all([opening, loading]);
        return;
      }
      void opening;
    }
    await loading;
  }

  return {
    loadSourceDocument,
    closeSourceDocument,
    previewSourceDocument,
    nextLoadId,
    invalidateLoad,
  };
}

export function useSourceDocument(host: SourceDocumentHost): SourceDocumentController {
  const hostRef = useRef(host);
  hostRef.current = host;
  const controllerRef = useRef<SourceDocumentController | null>(null);
  if (!controllerRef.current) {
    controllerRef.current = createSourceDocumentController(() => hostRef.current);
  }
  return controllerRef.current;
}
