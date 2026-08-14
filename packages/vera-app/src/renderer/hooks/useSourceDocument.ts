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

  async function previewSourceDocument(entry: FolderEntry) {
    if (entry.type !== 'vera' && entry.type !== 'pdf') return;
    const host = getHost();
    if (host.pendingSourcePath) return;
    const selection: ExplorerSelection = { kind: 'file', path: entry.path, type: entry.type };
    const requestId = ++sourceDocumentLoadRef.current;
    host.setPendingSourcePath(entry.path);
    host.setLibraryInfoPath('');
    host.setExplorerSelection(selection);
    host.setSelected(null);
    host.setViewerMode('document');
    host.setViewerCollapsed(false);
    if (entry.type === 'vera') {
      await host.openTargetPath(entry.path, { preserveLibrary: true });
    } else {
      host.applyConvertDefaultsFromSelection(selection);
    }
    if (requestId !== sourceDocumentLoadRef.current) return;
    await loadSourceDocument(entry.path, true, requestId);
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
