import React, { type CSSProperties, useEffect, useMemo, useReducer, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  FileInput,
  Folder,
  FolderOpen,
  ListChecks,
  Maximize2,
  MessageSquareText,
  Minimize2,
  PanelLeftClose,
  PanelLeftOpen,
  PanelRightClose,
  PanelRightOpen,
  Plus,
  RefreshCw,
  Search,
  Settings,
  Terminal,
  Trash2,
  X,
} from 'lucide-react';
import { ActivityTrace } from './components/activity/ActivityTrace';
import { TraceView } from './components/activity/TraceView';
import { AppStatusBar } from './components/AppStatusBar';
import { ChatComposer } from './components/ChatComposer';
import { ChatTurn } from './components/ChatTurn';
import { ConvertPanel } from './components/ConvertPanel';
import { DocumentInfoPanel } from './components/DocumentInfoPanel';
import { ExplorerPanel } from './components/ExplorerPanel';
import { LibraryIndexModal, type IndexPrompt } from './components/LibraryIndexModal';
import { PdfSourceViewer } from './components/PdfSourceViewer';
import { ModelManager, ProviderManager } from './components/ProviderManagers';
import { mergePipelineFieldValues } from './components/PipelineConfigForm';
import { VeraIcon } from './components/VeraIcon';
import { useAppBootstrap } from './hooks/useAppBootstrap';
import { DEFAULT_ACTION_TIMEOUT_MS, useSidecarCall } from './hooks/useSidecarCall';
import { useWorkspaceFolders } from './hooks/useWorkspaceFolders';
import { firstCitationInAnswer } from './lib/citations';
import { backgroundTasksReducer, type BackgroundTask } from './lib/backgroundTasks';
import { EMPTY_FIGURES, EMPTY_REGIONS } from './lib/constants';
import { awaitConversionRequest } from './lib/conversion';
import {
  convertDefaultsFromSelection,
  fileName,
  formatBox,
  formatPages,
  isPathInsideFolder,
  isPdfSource,
  sameFsPath,
  showInFolderLabel,
  siblingPdfPath,
  type ExplorerSelection,
} from './lib/formatting';
import { INDEX_STATUSES_STORAGE_KEY } from './lib/workspaceFolders';
import { figureCacheKey, mergeFigureData, sameSearchResult } from './lib/figures';
import {
  routeOpenTarget,
  syncCollapsedFolders,
  type ExplorerFileFilter,
} from './lib/explorer';
import {
  findSiblingPdfPath,
  reconvertExportGate,
  reconvertInspectFailedMessage,
  reconvertMissingSourceMessage,
  reconvertPipelineOptionsFromInspect,
  reconvertPrefillFromInspect,
  resolveReconvertPdf,
} from './lib/reconvert';
import { defaultEnabledModels, filterDiscoveredModels, providerDisplayName, REASONING_EFFORTS, reasoningEffortLabel } from './lib/providers';
import type { AppSettings, BatchConvertResult, ChatAnswerResult, ChatAttachment, ChatCitationResult, ExportResult, FigureResult, FolderEntry, InspectResult, LibraryIndexBuildReport, LibraryIndexStatus, Mode, PageResult, PipelineDescriptor, PipelineOptions, ProviderProfile, SearchResult, Session, SessionTurn, StreamEvent, SourceDocumentResult, ValidateResult } from './types';
import './styles.css';

type SideView = 'explorer' | 'chats' | 'convert';
type CenterView = 'chat' | 'search';
type ViewerMode = 'selection' | 'document' | 'info';

const SOURCE_LOAD_TIMEOUT_MS = 2 * 60 * 1000;

// In-memory store for LLM traces. Traces are large (full prompt/response dumps),
// so we keep them only for the lifetime of this app window instead of writing them
// to the on-disk session store. They survive switching between sessions but are
// discarded when the app is closed (window reload). Keyed by `${sessionId}:${turnTimestamp}`.
const traceMemory = new Map<string, StreamEvent[]>();

function traceKey(sessionId: string, timestamp: number): string {
  return `${sessionId}:${timestamp}`;
}

function stripTrace(turn: SessionTurn): SessionTurn {
  if (!turn.trace) return turn;
  const { trace: _trace, ...rest } = turn;
  return rest;
}

function App() {
  const customTitlebar = Boolean(window.vera.platform && window.vera.platform !== 'darwin');
  const workspaceRef = useRef<HTMLDivElement | null>(null);
  const [backgroundTasks, dispatchBackgroundTask] = useReducer(backgroundTasksReducer, []);
  const [sideView, setSideView] = useState<SideView>('explorer');
  const [centerView, setCenterView] = useState<CenterView>('chat');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [viewerMode, setViewerMode] = useState<ViewerMode>('document');
  const [path, setPath] = useState('');
  const [activeLibraryPath, setActiveLibraryPath] = useState('');
  const [indexStatuses, setIndexStatuses] = useState<Record<string, LibraryIndexStatus>>({});
  const [indexStatusChecking, setIndexStatusChecking] = useState<Record<string, boolean>>({});
  const [indexReports, setIndexReports] = useState<Record<string, LibraryIndexBuildReport>>({});
  const [indexPrompt, setIndexPrompt] = useState<IndexPrompt | null>(null);
  const [indexReport, setIndexReport] = useState<LibraryIndexBuildReport | null>(null);
  const [indexRecursive, setIndexRecursive] = useState(true);
  const [indexExcludes, setIndexExcludes] = useState('');
  const dismissedIndexStates = useRef(new Map<string, string>());
  const suppressedIndexPrompts = useRef(new Set<string>(
    (() => {
      try {
        const stored = JSON.parse(localStorage.getItem('vera.suppressedIndexPrompts') || '[]');
        return Array.isArray(stored) ? stored.filter((path): path is string => typeof path === 'string') : [];
      } catch {
        return [];
      }
    })(),
  ));
  const [suppressIndexPrompt, setSuppressIndexPrompt] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [submittedSearchQuery, setSubmittedSearchQuery] = useState('');
  const [composerResetVersion, setComposerResetVersion] = useState(0);
  const [composerRestoredDraft, setComposerRestoredDraft] = useState({ version: 0, text: '' });
  const [attachments, setAttachments] = useState<ChatAttachment[]>([]);
  const [mode, setMode] = useState('hybrid');
  const [topK, setTopK] = useState(8);
  const [contextChunks, setContextChunks] = useState(0);
  const [includeFigures, setIncludeFigures] = useState(true);
  const [providers, setProviders] = useState<ProviderProfile[]>([]);
  const [activeProviderId, setActiveProviderId] = useState('');
  const [activeModel, setActiveModel] = useState('');
  const [modes, setModes] = useState<Mode[]>([]);
  const [activeModeId, setActiveModeId] = useState('');
  const [embeddingModel, setEmbeddingModel] = useState('hashing');
  const [embeddingProviders, setEmbeddingProviders] = useState<string[]>([]);
  const [ingestPipeline, setIngestPipeline] = useState('pymupdf');
  const [ingestPipelineDescriptors, setIngestPipelineDescriptors] = useState<PipelineDescriptor[]>([]);
  const [ingestPipelineConfigs, setIngestPipelineConfigs] = useState<Record<string, PipelineOptions>>({});
  const [pipelineOptions, setPipelineOptions] = useState<PipelineOptions>({});
  const [hasHfToken, setHasHfToken] = useState(false);
  const [modePickerOpen, setModePickerOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [modelPickerOpen, setModelPickerOpen] = useState(false);
  const [modelFilter, setModelFilter] = useState('');
  const [hoveredModelOptions, setHoveredModelOptions] = useState<{
    providerId: string;
    model: string;
  } | null>(null);
  const [modelManagerOpen, setModelManagerOpen] = useState(false);
  const [modelRefreshBusyId, setModelRefreshBusyId] = useState('');
  const [modelRefreshMessage, setModelRefreshMessage] = useState('');
  const [convertMode, setConvertMode] = useState<'batch' | 'selected'>('selected');
  const [batchDirectory, setBatchDirectory] = useState('');
  const [batchRecursive, setBatchRecursive] = useState(true);
  const [batchOverwrite, setBatchOverwrite] = useState(false);
  const [explorerSelection, setExplorerSelection] = useState<ExplorerSelection | null>(null);
  const [selectedPdfs, setSelectedPdfs] = useState<string[]>([]);
  const [reconvertNotice, setReconvertNotice] = useState<string | null>(null);
  const [reconvertBusy, setReconvertBusy] = useState(false);
  const reconvertInFlightRef = useRef(false);
  const reconvertDefaultsRef = useRef<{ overwrite: boolean; storeOriginal: boolean } | null>(null);
  const [storeOriginal, setStoreOriginal] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [providerErrorDetail, setProviderErrorDetail] = useState<string | null>(null);
  const { call, cancelActionScope } = useSidecarCall({
    dispatchBackgroundTask,
    setErrorMessage,
    setProviderErrorDetail,
  });
  const [inspect, setInspect] = useState<InspectResult | null>(null);
  const libraryInspectCache = useRef(new Map<string, InspectResult>());
  const [validation, setValidation] = useState<ValidateResult | null>(null);
  const [batchConvertResult, setBatchConvertResult] = useState<BatchConvertResult | null>(null);
  const [conversionError, setConversionError] = useState<string | null>(null);
  const conversionRequestIdRef = useRef<string | null>(null);
  const conversionProgressCleanupRef = useRef<{ requestId: string; off: () => void } | null>(null);
  const conversionCanceledRef = useRef(false);
  const conversionInterruptRef = useRef<'stop' | 'skip' | null>(null);
  const [exportResult, setExportResult] = useState<ExportResult | null>(null);
  const [sourceDocument, setSourceDocument] = useState<SourceDocumentResult | null>(null);
  const [sourceDocumentPath, setSourceDocumentPath] = useState('');
  const [pendingSourcePath, setPendingSourcePath] = useState('');
  const [libraryInfoPath, setLibraryInfoPath] = useState('');
  const sourceDocumentLoadRef = useRef(0);
  const inspectGenerationRef = useRef(0);
  const figureDataLoadRef = useRef(0);
  const sourceLoading = Boolean(pendingSourcePath);
  const figureDataCache = useRef(new Map<string, FigureResult>());
  const [pageNumber, setPageNumber] = useState(1);
  const [pageResult, setPageResult] = useState<PageResult | null>(null);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [selected, setSelected] = useState<SearchResult | null>(null);
  const [citationJumpVersion, setCitationJumpVersion] = useState(0);
  const [selectedFiles, setSelectedFiles] = useState<string[]>([]);
  const [selectionAnchorPath, setSelectionAnchorPath] = useState<string | null>(null);
  const [collapsedFolders, setCollapsedFolders] = useState<string[]>([]);
  const [explorerFileFilter, setExplorerFileFilter] = useState<ExplorerFileFilter>('vera');
  const [chatAnswer, setChatAnswer] = useState<ChatAnswerResult | null>(null);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [sessionTurns, setSessionTurns] = useState<SessionTurn[]>([]);
  const [streamEvents, setStreamEvents] = useState<StreamEvent[]>([]);
  const [traceEvents, setTraceEvents] = useState<StreamEvent[]>([]);
  const [failedTraceEvents, setFailedTraceEvents] = useState<StreamEvent[]>([]);
  const [streamingAnswer, setStreamingAnswer] = useState('');
  const [responseStatus, setResponseStatus] = useState('Thinking');
  const streamingAnswerRef = useRef('');
  const answerCanceledRef = useRef(false);
  const activeAnswerRequestIdRef = useRef<string | null>(null);
  const [showTrace, setShowTrace] = useState(() => {
    try {
      return localStorage.getItem('vera.showTrace') === '1';
    } catch {
      return false;
    }
  });

  const threadRef = useRef<HTMLDivElement | null>(null);
  const shouldAutoScrollThreadRef = useRef(true);
  const [showJumpToLatest, setShowJumpToLatest] = useState(false);
  const [sourcePaneWidth, setSourcePaneWidth] = useState(34);
  const [viewerCollapsed, setViewerCollapsed] = useState(false);
  const [viewerExpanded, setViewerExpanded] = useState(false);
  const [isResizingSource, setIsResizingSource] = useState(false);
  const [sidePanelWidth, setSidePanelWidth] = useState(() => {
    const stored = Number(localStorage.getItem('vera.sidePanelWidth'));
    if (stored === 300) return 260;
    return stored >= 200 && stored <= 600 ? stored : 260;
  });
  const [isResizingSide, setIsResizingSide] = useState(false);
  const openLibraryRef = useRef<(folderPath: string) => Promise<void> | void>(() => undefined);
  const refreshIndexStatusRef = useRef<(
    folderPath: string,
    verifyHashes?: boolean,
  ) => Promise<LibraryIndexStatus | null>>(async () => null);
  const {
    folders,
    busyFolderPath,
    addFolderFromPath,
    addFolder,
    removeFolder,
    refreshFolder,
    loadFolders,
  } = useWorkspaceFolders({
    onOpenLibrary: (folderPath) => openLibraryRef.current(folderPath),
    onFolderRemoved: (folderPath) => {
      libraryInspectCache.current.delete(folderPath);
      setSelectedPdfs((prev) => prev.filter((entry) => !isPathInsideFolder(entry, folderPath)));
      setSelectedFiles((prev) => prev.filter((entry) => !isPathInsideFolder(entry, folderPath)));
      setSelectionAnchorPath((current) => (
        current && isPathInsideFolder(current, folderPath) ? null : current
      ));
      setExplorerSelection((current) => (
        current && isPathInsideFolder(current.path, folderPath) ? null : current
      ));
      if (libraryInfoPath && isPathInsideFolder(libraryInfoPath, folderPath)) {
        setLibraryInfoPath('');
      }
      if (
        (sourceDocumentPath && isPathInsideFolder(sourceDocumentPath, folderPath))
        || (pendingSourcePath && isPathInsideFolder(pendingSourcePath, folderPath))
      ) {
        cancelActionScope('source');
        sourceDocumentLoadRef.current += 1;
        setSourceDocument(null);
        setSourceDocumentPath('');
        setPendingSourcePath('');
      }
      setInspect((current) => {
        const currentPath = current?.directory || current?.path || current?.file || '';
        return currentPath && isPathInsideFolder(currentPath, folderPath) ? null : current;
      });
      if (activeLibraryPath === folderPath) {
        setActiveLibraryPath('');
        try { localStorage.removeItem('vera.activeLibraryPath'); } catch { /* ignore persistence errors */ }
      }
      setIndexStatuses((prev) => {
        const next = { ...prev };
        delete next[folderPath];
        try {
          localStorage.setItem(INDEX_STATUSES_STORAGE_KEY, JSON.stringify(next));
        } catch {
          // Index-state caching only improves startup feedback.
        }
        return next;
      });
    },
    refreshIndexStatus: (folderPath, verifyHashes) => refreshIndexStatusRef.current(folderPath, verifyHashes),
    onIndexStatusesHydrated: setIndexStatuses,
    onWatchedFolderChanged: (folderPath) => {
      dismissedIndexStates.current.delete(folderPath);
    },
    onFolderWillRefresh: (folderPath) => {
      libraryInspectCache.current.delete(folderPath);
    },
    onFolderRefreshed: (folderPath) => {
      if (activeLibraryPath === folderPath && path === folderPath) {
        setInspect(null);
      }
    },
  });
  const indexingFolders = useMemo(
    () => Object.fromEntries(
      backgroundTasks
        .filter((task) => task.kind === 'index' && task.path && task.operation)
        .map((task) => [task.path as string, task.operation as 'build' | 'update']),
    ) as Record<string, 'build' | 'update'>,
    [backgroundTasks],
  );
  const conversionTask = backgroundTasks.find((task) => task.kind === 'conversion') ?? null;
  const operationTasks = backgroundTasks.filter((task) => task.kind === 'operation');
  const inspectionTasks = backgroundTasks.filter((task) => task.kind === 'inspection');
  const activeOperation = operationTasks[operationTasks.length - 1] ?? null;
  const conversionInProgress = Boolean(conversionTask);
  const convertLocked = conversionInProgress || reconvertBusy;
  const conversionStatus = conversionTask?.message ?? null;
  const busyAction = activeOperation?.label ?? null;
  const chatBusy = operationTasks.some((task) => task.label === 'Asking');
  const searchBusy = operationTasks.some((task) => task.label === 'Searching');

  const searchScopePath = activeLibraryPath || path;
  const activeIndexStatus = activeLibraryPath ? indexStatuses[activeLibraryPath] : undefined;
  const activeLibraryIsEmpty = Boolean(
    activeLibraryPath
    && selectedFiles.length === 0
    && path === activeLibraryPath
    && inspect?.directory
    && inspect.discovered_file_count === 0,
  );
  // Explicit checkbox selections are a valid scope even when the active library
  // inspection is empty or a document/folder has not been opened in the viewer.
  const hasSearchableScope = selectedFiles.length > 0 || (Boolean(searchScopePath.trim()) && !activeLibraryIsEmpty);
  const isCorpus = Boolean(
    (activeLibraryPath && path === activeLibraryPath)
    || inspect?.directory
    || (path && !path.toLowerCase().endsWith('.vera'))
    || selectedFiles.length > 1,
  );
  const viewerInfoPath = sourceDocumentPath || libraryInfoPath;
  const viewerInfoIsCorpus = Boolean(libraryInfoPath && viewerInfoPath === libraryInfoPath);
  const viewerInfoIsArchive = Boolean(
    viewerInfoPath && viewerInfoPath.toLowerCase().endsWith('.vera'),
  );
  const viewerInfoInspectable = Boolean(
    viewerInfoPath
    && (viewerInfoIsCorpus || viewerInfoIsArchive),
  );
  const inspectedPath = inspect?.directory || inspect?.path || inspect?.file || '';
  const viewerInspect = inspectedPath.replace(/\\/g, '/').toLowerCase()
    === viewerInfoPath.replace(/\\/g, '/').toLowerCase()
    ? inspect
    : null;
  const viewerIndexStatus = viewerInfoIsCorpus
    ? indexStatuses[viewerInfoPath] ?? viewerInspect?.index
    : undefined;
  const busy = operationTasks.length > 0 || inspectionTasks.length > 0;
  const activeProvider = useMemo(
    () => providers.find((profile) => profile.id === activeProviderId) ?? null,
    [providers, activeProviderId],
  );
  const activeModelOptions = activeProvider?.model_options?.[activeModel] ?? {};
  const activeMode = useMemo(
    () => modes.find((entry) => entry.id === activeModeId) ?? modes.find((entry) => entry.id === 'ask') ?? modes[0] ?? null,
    [modes, activeModeId],
  );

  const citation = useMemo(() => {
    if (!selected) return 'No result selected';
    const source = selected.file || selected.source_filename || 'document';
    return `${source} · p. ${formatPages(selected.page_start, selected.page_end)}`;
  }, [selected]);
  const viewerTitle = useMemo(() => {
    if (viewerMode === 'info') {
      if (viewerInfoIsCorpus) {
        return {
          primary: viewerInfoPath ? fileName(viewerInfoPath) : 'Library Info',
          secondary: viewerInfoPath ? 'Library Info' : 'No library selected',
          title: viewerInfoPath,
        };
      }
      const pathOrName = viewerInfoPath || sourceDocument?.filename || '';
      return {
        primary: pathOrName ? fileName(pathOrName) : 'Document Info',
        secondary: pathOrName ? 'Document Info' : 'No document loaded',
        title: pathOrName,
      };
    }
    if (selected && viewerMode === 'selection') {
      const source = selected.file || selected.source_filename || sourceDocument?.filename || '';
      return {
        primary: source ? fileName(source) : 'Chunk Details',
        secondary: `p. ${formatPages(selected.page_start, selected.page_end)}`,
        title: citation,
      };
    }
    const name = pendingSourcePath || sourceDocument?.filename || sourceDocumentPath || '';
    if (name) {
      return {
        primary: fileName(name),
        secondary: pendingSourcePath ? 'Loading…' : null as string | null,
        title: pendingSourcePath || sourceDocumentPath || name,
      };
    }
    return {
      primary: 'Document Viewer',
      secondary: 'No document loaded',
      title: '',
    };
  }, [
    citation,
    pendingSourcePath,
    selected,
    sourceDocument,
    sourceDocumentPath,
    viewerInfoIsCorpus,
    viewerInfoPath,
    viewerMode,
  ]);
  const selectedChunkIndex = useMemo(() => {
    if (!selected) return -1;
    const exactIndex = results.indexOf(selected);
    if (exactIndex >= 0) return exactIndex;
    const selectedSource = selected.file || selected.source_filename || '';
    return results.findIndex((result) => (
      result.chunk_id === selected.chunk_id
      && (result.file || result.source_filename || '') === selectedSource
    ));
  }, [results, selected]);

  const selectedSourcePath = selected?.file || path;
  const selectedTargetPage = selected?.regions?.find((region) => region.page_number)?.page_number ?? selected?.page_start ?? null;
  // Keep these props referentially stable so PdfSourceViewer's memoization can
  // isolate its DOM-heavy PDF tree from chat-composer keystrokes.
  const viewerHighlights = useMemo(() => {
    if (!selected) {
      return { regions: EMPTY_REGIONS, figures: EMPTY_FIGURES, targetPage: null };
    }
    // Only suppress overlays when a different archive is still on screen.
    const normalize = (value: string) => value.replace(/\\/g, '/').toLowerCase();
    if (
      sourceDocumentPath
      && selectedSourcePath
      && normalize(sourceDocumentPath) !== normalize(selectedSourcePath)
    ) {
      return { regions: EMPTY_REGIONS, figures: EMPTY_FIGURES, targetPage: null };
    }
    return {
      regions: selected.regions || EMPTY_REGIONS,
      figures: selected.figures?.filter((figure) => figure.included_in_context) || EMPTY_FIGURES,
      targetPage: selectedTargetPage,
    };
  }, [selected, selectedSourcePath, selectedTargetPage, sourceDocumentPath]);

  function applyConvertDefaultsFromSelection(selection: ExplorerSelection | null = explorerSelection) {
    const defaults = convertDefaultsFromSelection(selection, activeLibraryPath);
    if (!defaults?.batchDirectory) return;
    setBatchDirectory(defaults.batchDirectory);
  }

  function snapshotConvertDefaultsForReconvert() {
    if (reconvertDefaultsRef.current) return;
    reconvertDefaultsRef.current = { overwrite: batchOverwrite, storeOriginal };
  }

  function restoreConvertDefaultsAfterReconvert() {
    const snapshot = reconvertDefaultsRef.current;
    if (!snapshot) return;
    setBatchOverwrite(snapshot.overwrite);
    setStoreOriginal(snapshot.storeOriginal);
    reconvertDefaultsRef.current = null;
  }

  function openSide(view: SideView, selectionOverride?: ExplorerSelection | null) {
    if (view === 'convert') {
      applyConvertDefaultsFromSelection(
        selectionOverride !== undefined ? selectionOverride : explorerSelection,
      );
      if (selectedPdfs.length > 0) {
        setConvertMode('selected');
      }
      setReconvertNotice(null);
    } else {
      restoreConvertDefaultsAfterReconvert();
    }
    setSideView(view);
    setSidebarCollapsed(false);
  }

  function openConvertSelected(paths?: string[]) {
    if (paths?.length) {
      setSelectedPdfs(paths);
      setExplorerSelection({ kind: 'file', path: paths[paths.length - 1], type: 'pdf' });
    }
    setReconvertNotice(null);
    setConvertMode('selected');
    setSideView('convert');
    setSidebarCollapsed(false);
  }

  function openConvertFolder(folderPath: string) {
    setReconvertNotice(null);
    setConversionError(null);
    setBatchDirectory(folderPath);
    setConvertMode('batch');
    setExplorerSelection({ kind: 'folder', path: folderPath });
    setSideView('convert');
    setSidebarCollapsed(false);
  }

  async function openReconvert(entry: FolderEntry, folderPath: string) {
    if (conversionInProgress || reconvertInFlightRef.current) return;
    reconvertInFlightRef.current = true;
    const folder = folders.find((item) => item.path === folderPath);
    const listedPdf = findSiblingPdfPath(entry.path, folder?.entries ?? []);
    snapshotConvertDefaultsForReconvert();
    setReconvertBusy(true);
    setConversionError(null);
    setBatchOverwrite(true);
    setConvertMode('selected');
    setSideView('convert');
    setSidebarCollapsed(false);
    setReconvertNotice(`Preparing to reconvert “${fileName(entry.path)}”…`);
    if (listedPdf) {
      setSelectedPdfs([listedPdf]);
      setExplorerSelection({ kind: 'file', path: listedPdf, type: 'pdf' });
    }
    const reconvertCall = { scope: 'reconvert', timeoutMs: DEFAULT_ACTION_TIMEOUT_MS };
    let prepared = false;
    try {
      const sibling = siblingPdfPath(entry.path);
      const siblingExists = Boolean(listedPdf) || (sibling ? await window.vera.pathExists(sibling) : false);
      const resolution = resolveReconvertPdf(entry.path, {
        entries: folder?.entries ?? [],
        siblingExists,
      });
      const inspectResult = await call<InspectResult>(
        { action: 'inspect', path: entry.path },
        'Preparing reconvert',
        undefined,
        reconvertCall,
      );
      const prefill = reconvertPrefillFromInspect(inspectResult);

      let pdfPath: string | null = listedPdf;
      let restoredFromArchive = false;
      if (resolution.status === 'ready') {
        pdfPath = resolution.pdfPath;
      } else if (resolution.status === 'export') {
        const gate = reconvertExportGate({
          inspectOk: inspectResult !== null,
          hasEmbeddedSource: prefill.hasEmbeddedSource,
        });
        if (!gate.allow) {
          setReconvertNotice(null);
          setConversionError(
            gate.reason === 'inspect-failed'
              ? reconvertInspectFailedMessage()
              : reconvertMissingSourceMessage(entry.path),
          );
          return;
        }
        const exported = await call<ExportResult>(
          { action: 'export', path: entry.path, output: resolution.pdfPath },
          'Restoring embedded PDF',
          undefined,
          reconvertCall,
        );
        if (exported?.output) {
          pdfPath = exported.output;
          restoredFromArchive = true;
          void refreshFolder(folderPath, { showBusy: false }).catch((error) => {
            console.error('Unable to refresh folder after restoring source PDF', error);
          });
        } else {
          setReconvertNotice(null);
          setConversionError(reconvertMissingSourceMessage(entry.path));
          return;
        }
      } else {
        setReconvertNotice(null);
        setConversionError(reconvertMissingSourceMessage(entry.path));
        return;
      }

      if (!pdfPath) {
        setReconvertNotice(null);
        setConversionError(reconvertMissingSourceMessage(entry.path));
        return;
      }

      if (prefill.embeddingModel) setEmbeddingModel(prefill.embeddingModel);
      const nextPipeline = prefill.ingestPipeline || ingestPipeline;
      const nextDescriptor = ingestPipelineDescriptors.find(
        (item) => item.spec === nextPipeline || item.provider === nextPipeline,
      ) ?? null;
      const inspectOptions = reconvertPipelineOptionsFromInspect(inspectResult);
      const mergedOptions = mergePipelineFieldValues(nextDescriptor, {
        ...ingestPipelineConfigs[nextPipeline],
        ...inspectOptions,
      });
      if (prefill.ingestPipeline) setIngestPipeline(prefill.ingestPipeline);
      setIngestPipelineConfigs((prev) => ({ ...prev, [nextPipeline]: mergedOptions }));
      setPipelineOptions(mergedOptions);
      if (prefill.hasEmbeddedSource || restoredFromArchive) {
        setStoreOriginal(true);
      }

      setSelectedPdfs([pdfPath]);
      setExplorerSelection({ kind: 'file', path: pdfPath, type: 'pdf' });
      setReconvertNotice(
        restoredFromArchive
          ? 'Restored the embedded PDF beside this archive. Overwrite is on so Convert will replace the existing .vera. Choose a different pipeline or embedding if you want, then convert. Update the library index afterward if this folder is indexed.'
          : 'Overwrite is on so Convert will replace the existing .vera. The pipeline and embedding below start from this archive — change them if you want, then convert. Update the library index afterward if this folder is indexed.',
      );
      prepared = true;
    } catch (error) {
      setReconvertNotice(null);
      setConversionError(error instanceof Error ? error.message : reconvertMissingSourceMessage(entry.path));
    } finally {
      reconvertInFlightRef.current = false;
      setReconvertBusy(false);
      if (!prepared) restoreConvertDefaultsAfterReconvert();
    }
  }

  function toggleSelectedPdf(pdfPathValue: string) {
    setSelectedPdfs((prev) => {
      if (prev.includes(pdfPathValue)) {
        return prev.filter((entry) => entry !== pdfPathValue);
      }
      return [...prev, pdfPathValue];
    });
  }

  async function choosePdfs() {
    const paths = (await window.vera.pickPdf()).map((entry) => entry.trim()).filter(Boolean);
    if (!paths.length) return;
    setSelectedPdfs((prev) => {
      const merged = [...prev];
      for (const filePath of paths) {
        if (!merged.includes(filePath)) merged.push(filePath);
      }
      return merged;
    });
    setExplorerSelection({ kind: 'file', path: paths[paths.length - 1], type: 'pdf' });
    setConvertMode('selected');
    setBatchConvertResult(null);
  }

  function selectExplorerFolder(folderPath: string) {
    setLibraryInfoPath('');
    setSelected(null);
    setViewerMode('document');
    setExplorerSelection({ kind: 'folder', path: folderPath });
    void openTargetPath(folderPath, { asLibrary: true });
  }

  async function openLibraryInfo(folderPath: string) {
    selectExplorerFolder(folderPath);
    cancelActionScope('source');
    sourceDocumentLoadRef.current += 1;
    const generation = ++inspectGenerationRef.current;
    setSourceDocument(null);
    setSourceDocumentPath('');
    setPendingSourcePath('');
    setLibraryInfoPath(folderPath);
    setSelected(null);
    setErrorMessage(null);
    setViewerMode('info');
    setViewerCollapsed(false);
    setViewerExpanded(false);
    const response = await window.vera.request<InspectResult>({
      action: 'inspect',
      path: folderPath,
      summary_only: true,
      default_recursive: true,
      allow_empty: true,
    });
    if (generation !== inspectGenerationRef.current) return;
    if (response.ok && response.result) {
      libraryInspectCache.current.set(folderPath, response.result);
      setInspect(response.result);
    }
  }

  function indexStateKey(value: LibraryIndexStatus): string {
    return `${value.exists}:${value.fresh}:${value.reasons.join('|')}`;
  }

  function presentIndexPrompt(folderPath: string, value: LibraryIndexStatus) {
    if (value.fresh || indexingFolders[folderPath]) return;
    const key = indexStateKey(value);
    if (suppressedIndexPrompts.current.has(folderPath) || dismissedIndexStates.current.get(folderPath) === key) return;
    setIndexRecursive(value.exists ? Boolean(value.recursive) : true);
    setIndexExcludes(value.excludes?.join('\n') ?? '');
    setSuppressIndexPrompt(suppressedIndexPrompts.current.has(folderPath));
    setIndexReport(null);
    setIndexPrompt({ path: folderPath, status: value });
  }

  function persistSuppressedIndexPrompts() {
    try {
      localStorage.setItem('vera.suppressedIndexPrompts', JSON.stringify([...suppressedIndexPrompts.current]));
    } catch {
      // Prompt preferences are a convenience and may be unavailable in restricted storage.
    }
  }

  async function promptForIndexBeforeQuery(): Promise<boolean> {
    if (!activeLibraryPath || selectedFiles.length > 0) return false;
    const value = activeIndexStatus ?? await refreshIndexStatus(activeLibraryPath);
    if (!value || value.fresh || suppressedIndexPrompts.current.has(activeLibraryPath)) return false;
    if (indexPrompt || dismissedIndexStates.current.get(activeLibraryPath) === indexStateKey(value)) return false;
    presentIndexPrompt(activeLibraryPath, value);
    return true;
  }

  async function refreshIndexStatus(folderPath: string, verifyHashes = false): Promise<LibraryIndexStatus | null> {
    setIndexStatusChecking((prev) => ({ ...prev, [folderPath]: true }));
    try {
      const response = await window.vera.request<LibraryIndexStatus>({
        action: 'index_status',
        path: folderPath,
        verify_hashes: verifyHashes,
      });
      if (!response.ok || !response.result) return null;
      const value = response.result;
      setIndexStatuses((prev) => {
        const next = { ...prev, [folderPath]: value };
        try {
          localStorage.setItem('vera.indexStatuses', JSON.stringify(next));
        } catch {
          // Index-state caching only improves startup feedback.
        }
        return next;
      });
      return value;
    } catch {
      return null;
    } finally {
      setIndexStatusChecking((prev) => {
        const next = { ...prev };
        delete next[folderPath];
        return next;
      });
    }
  }

  function parentFolderForPath(filePath: string): string | undefined {
    return folders.find((folder) => folder.entries.some((entry) => entry.path === filePath))?.path;
  }

  function clearExplorerFileSelection() {
    const scopedVera = !activeLibraryPath && Boolean(path) && path.toLowerCase().endsWith('.vera');
    const hadFileSelection = selectedPdfs.length > 0
      || selectedFiles.length > 0
      || explorerSelection?.kind === 'file'
      || scopedVera;
    if (!hadFileSelection) return false;

    setSelectedPdfs([]);
    setSelectedFiles([]);
    setSelectionAnchorPath(null);

    if (scopedVera) {
      const parent = parentFolderForPath(path);
      if (parent) {
        setExplorerSelection({ kind: 'folder', path: parent });
        void openTargetPath(parent, { asLibrary: true });
        return true;
      }
      setExplorerSelection(null);
      updateTargetPath('');
      return true;
    }

    if (explorerSelection?.kind === 'file') {
      setExplorerSelection(null);
    }
    return true;
  }

  function handleExplorerBlankPointer(event: { button?: number; currentTarget: HTMLElement; target: EventTarget | null }) {
    if (event.button !== undefined && event.button !== 0) return;
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    // Only pane chrome / tree padding — not 1px gaps between file rows.
    if (target !== event.currentTarget && !target.classList.contains('explorerTree')) {
      return;
    }
    event.currentTarget.focus({ preventScroll: true });
    clearExplorerFileSelection();
  }

  async function previewSourceDocument(entry: FolderEntry) {
    if (entry.type !== 'vera' && entry.type !== 'pdf') return;
    // Ignore further explorer opens while a document is loading so repeated
    // double-clicks do not stack work when feedback is easy to miss.
    if (pendingSourcePath) return;
    const selection: ExplorerSelection = { kind: 'file', path: entry.path, type: entry.type };
    const requestId = ++sourceDocumentLoadRef.current;
    setPendingSourcePath(entry.path);
    setLibraryInfoPath('');
    setExplorerSelection(selection);
    setSelected(null);
    setViewerMode('document');
    setViewerCollapsed(false);
    if (entry.type === 'vera') {
      await openTargetPath(entry.path, { preserveLibrary: true });
    } else {
      applyConvertDefaultsFromSelection(selection);
    }
    // A newer open/close may have invalidated this preview while inspect ran.
    // That successor owns pendingSourcePath clearing.
    if (requestId !== sourceDocumentLoadRef.current) return;
    await loadSourceDocument(entry.path, true, requestId);
  }

  async function trashEntry(entry: FolderEntry, folderPath: string) {
    try {
      const result = await window.vera.trashWorkspaceFile(entry.path, folderPath);
      if (result === 'cancelled') return;
      setSelectedFiles((files) => files.filter((file) => file !== entry.path));
      setSelectedPdfs((files) => files.filter((file) => file !== entry.path));
      if (path === entry.path) updateTargetPath(activeLibraryPath || '');
      // Scope and viewer are independent — only blank the viewer when its open file is gone.
      if (sourceDocumentPath === entry.path || pendingSourcePath === entry.path) {
        cancelActionScope('source');
        sourceDocumentLoadRef.current += 1;
        setSourceDocument(null);
        setSourceDocumentPath('');
        setPendingSourcePath('');
      }
      await refreshFolder(folderPath);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Unable to move file to the Recycle Bin');
    }
  }

  async function revealInFolder(targetPath: string) {
    const label = showInFolderLabel(window.vera.platform);
    try {
      await window.vera.showInFolder(targetPath);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : `Unable to ${label.toLowerCase()}`);
    }
  }

  function clampSourcePaneWidth(value: number): number {
    return Math.min(70, Math.max(32, value));
  }

  function clampSidePanelWidth(value: number): number {
    return Math.min(600, Math.max(200, value));
  }

  function resizeSidePanel(clientX: number) {
    const bounds = workspaceRef.current?.getBoundingClientRect();
    if (!bounds) return;
    setSidePanelWidth(clampSidePanelWidth(clientX - bounds.left));
  }

  function resizeSourcePane(clientX: number) {
    const bounds = workspaceRef.current?.getBoundingClientRect();
    if (!bounds) return;
    const widthFromRight = bounds.right - clientX;
    setSourcePaneWidth(clampSourcePaneWidth((widthFromRight / bounds.width) * 100));
  }

  async function openTargetPath(
    value: string,
    options: { asLibrary?: boolean; preserveLibrary?: boolean } = {},
  ) {
    const asLibrary = options.asLibrary ?? (
      folders.some((folder) => folder.path === value) || !value.toLowerCase().endsWith('.vera')
    );
    if (asLibrary) {
      inspectGenerationRef.current += 1;
      setActiveLibraryPath(value);
      try { localStorage.setItem('vera.activeLibraryPath', value); } catch { /* ignore persistence errors */ }
      setSelectedFiles([]);
      setSelectionAnchorPath(null);
      setPath(value);
      setValidation(null);
      setExportResult(null);
      setPageResult(null);
      const cached = libraryInspectCache.current.get(value);
      if (cached) {
        setInspect(cached);
        if (cached.index) {
          setIndexStatuses((prev) => ({ ...prev, [value]: cached.index! }));
        }
      } else {
        setInspect(null);
      }
      // Activation only sets search scope. Corpus open happens on first Search/Ask.
      // Querying a library with a missing or stale index prompts for an index then.
      void refreshIndexStatus(value);
      return;
    }
    if (!options.preserveLibrary) {
      setActiveLibraryPath('');
      try { localStorage.removeItem('vera.activeLibraryPath'); } catch { /* ignore persistence errors */ }
      setSelectedFiles([]);
    }
    const generation = ++inspectGenerationRef.current;
    updateTargetPath(value);
    const result = await call<InspectResult>({ action: 'inspect', path: value }, 'Opening');
    if (result && generation === inspectGenerationRef.current) {
      setInspect(result);
      setValidation(null);
    }
  }

  openLibraryRef.current = (folderPath) => openTargetPath(folderPath, { asLibrary: true });
  refreshIndexStatusRef.current = refreshIndexStatus;

  function updateTargetPath(value: string) {
    // Changing Search/Ask scope must not clear the document viewer. Preview and
    // citation loads replace the open source explicitly; trash clears it when
    // the open file is removed.
    setPath(value);
    setInspect(null);
    setValidation(null);
    setExportResult(null);
    setPageResult(null);
  }

  async function chooseBatchDirectory() {
    const chosen = await window.vera.pickFolder();
    if (chosen) {
      setBatchDirectory(chosen);
      setBatchConvertResult(null);
    }
  }

  async function inspectTarget(targetPath = path) {
    if (backgroundTasks.some((task) => task.kind === 'inspection' && task.path === targetPath)) return;
    const isLibrary = folders.some((folder) => folder.path === targetPath);
    const generation = ++inspectGenerationRef.current;
    const inspectionRequestId = crypto.randomUUID();
    dispatchBackgroundTask({
      type: 'start',
      task: {
        id: inspectionRequestId,
        kind: 'inspection',
        label: isLibrary ? 'Inspecting library' : 'Inspecting archive',
        path: targetPath,
        phase: 'inspecting',
        completed: 0,
        total: 0,
        chunks: 0,
        skipped: 0,
      },
    });
    const offProgress = window.vera.onAnswerEvent((event) => {
      if (event.id !== inspectionRequestId || event.event !== 'inspection_progress') return;
      dispatchBackgroundTask({
        type: 'update',
        id: inspectionRequestId,
        update: {
          phase: event.phase,
          completed: event.completed,
          total: event.total,
          currentItem: event.input?.trim() || undefined,
          chunks: event.chunks,
          skipped: event.skipped,
        },
      });
    });
    setErrorMessage(null);
    setProviderErrorDetail(null);
    try {
      const response = await window.vera.request<InspectResult>({
        action: 'inspect',
        path: targetPath,
        ...(targetPath === activeLibraryPath ? { recursive: activeIndexStatus?.recursive ?? true, excludes: activeIndexStatus?.excludes ?? [] } : {}),
      }, inspectionRequestId);
      if (generation !== inspectGenerationRef.current) return;
      if (!response.ok || !response.result) {
        throw new Error(response.error || 'Library inspection failed');
      }
      const result = response.result;
      if (result.directory) libraryInspectCache.current.set(targetPath, result);
      setInspect(result);
      setValidation(null);
      if (isLibrary) {
        void refreshIndexStatus(targetPath, true).then((refreshedStatus) => {
          if (!refreshedStatus || generation !== inspectGenerationRef.current) return;
          const cached = libraryInspectCache.current.get(targetPath);
          if (cached) {
            libraryInspectCache.current.set(targetPath, { ...cached, index: refreshedStatus });
          }
          setInspect((current) => {
            const currentPath = current?.directory || current?.path || current?.file || '';
            return sameFsPath(currentPath, targetPath)
              ? { ...current, index: refreshedStatus }
              : current;
          });
        });
      }
    } catch (error) {
      if (generation !== inspectGenerationRef.current) return;
      setErrorMessage(error instanceof Error ? error.message : 'Library inspection failed');
    } finally {
      offProgress();
      dispatchBackgroundTask({ type: 'finish', id: inspectionRequestId });
    }
  }

  function dismissIndexPrompt() {
    if (indexPrompt) {
      dismissedIndexStates.current.set(indexPrompt.path, indexStateKey(indexPrompt.status));
      if (suppressIndexPrompt) {
        suppressedIndexPrompts.current.add(indexPrompt.path);
        persistSuppressedIndexPrompts();
      }
    }
    setIndexPrompt(null);
    setIndexReport(null);
    setSuppressIndexPrompt(false);
  }

  async function startLibraryIndex(
    folderPath: string,
    operation: 'build' | 'update',
    options: { recursive?: boolean; excludes?: string[] } = {},
  ) {
    if (indexingFolders[folderPath]) return;
    const action = operation === 'build' ? 'index_build' : 'index_update';
    setIndexPrompt(null);
    setIndexReport(null);
    setIndexReports((prev) => {
      const next = { ...prev };
      delete next[folderPath];
      return next;
    });
    const indexRequestId = crypto.randomUUID();
    dispatchBackgroundTask({
      type: 'start',
      task: {
        id: indexRequestId,
        kind: 'index',
        label: operation === 'build' ? 'Building index' : 'Updating index',
        path: folderPath,
        operation,
        phase: 'discovering',
        completed: 0,
        total: 0,
        chunks: 0,
        skipped: 0,
      },
    });
    const offProgress = window.vera.onAnswerEvent((event) => {
      if (event.id !== indexRequestId || event.event !== 'index_progress') return;
      dispatchBackgroundTask({
        type: 'update',
        id: indexRequestId,
        update: {
          phase: event.phase,
          completed: event.completed,
          total: event.total,
          currentItem: event.input?.trim() || undefined,
          chunks: event.chunks,
          skipped: event.skipped,
        },
      });
    });
    let taskActive = true;
    const finishIndexTask = () => {
      if (!taskActive) return;
      offProgress();
      taskActive = false;
      dispatchBackgroundTask({ type: 'finish', id: indexRequestId });
    };
    setErrorMessage(null);
    try {
      const response = await window.vera.request<LibraryIndexBuildReport>({
        action,
        path: folderPath,
        ...(operation === 'build'
          ? {
              recursive: options.recursive ?? true,
              excludes: options.excludes ?? [],
            }
          : {}),
      }, indexRequestId);
      if (!response.ok || !response.result) {
        throw new Error(response.error || 'Library indexing failed');
      }
      const result = response.result;
      dismissedIndexStates.current.delete(folderPath);
      setIndexReports((prev) => ({ ...prev, [folderPath]: result }));
      finishIndexTask();
      libraryInspectCache.current.delete(folderPath);
      const [refreshed, inspectedResponse] = await Promise.all([
        refreshIndexStatus(folderPath),
        window.vera.request<InspectResult>({
          action: 'inspect',
          path: folderPath,
          summary_only: true,
          default_recursive: true,
          allow_empty: true,
        }),
      ]);
      if (inspectedResponse.ok && inspectedResponse.result) {
        const inspected = inspectedResponse.result;
        if (refreshed) inspected.index = refreshed;
        libraryInspectCache.current.set(folderPath, inspected);
        setInspect((current) => {
          const currentPath = current?.directory || current?.path || current?.file || '';
          return sameFsPath(currentPath, folderPath) ? inspected : current;
        });
      }
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Library indexing failed');
    } finally {
      finishIndexTask();
    }
  }

  async function manageLibraryIndex(folderPath: string) {
    if (indexingFolders[folderPath]) return;
    const value = indexStatuses[folderPath] ?? await refreshIndexStatus(folderPath);
    if (indexingFolders[folderPath]) return;
    const exists = Boolean(value?.exists);
    await startLibraryIndex(folderPath, exists ? 'update' : 'build', {
      recursive: exists ? Boolean(value?.recursive) : true,
      excludes: value?.excludes ?? [],
    });
  }

  async function confirmIndexAction() {
    if (!indexPrompt) return;
    const folderPath = indexPrompt.path;
    const operation = indexPrompt.status.exists ? 'update' : 'build';
    const excludes = indexExcludes.split(/\r?\n/).map((value) => value.trim()).filter(Boolean);
    await startLibraryIndex(folderPath, operation, {
      recursive: indexRecursive,
      excludes,
    });
  }

  async function searchTarget() {
    if (!hasSearchableScope) {
      setErrorMessage('This library does not contain any VERA documents yet.');
      return;
    }
    if (await promptForIndexBeforeQuery()) return;
    const result = await call<SearchResult[]>({
      action: 'search',
      path: searchScopePath,
      ...(selectedFiles.length ? { paths: selectedFiles } : {}),
      ...(activeLibraryPath && selectedFiles.length === 0
        ? { recursive: activeIndexStatus?.fresh ? activeIndexStatus.recursive ?? true : true, excludes: activeIndexStatus?.excludes ?? [] }
        : {}),
      query: searchQuery,
      mode,
      top_k: topK,
      context_chunks: contextChunks,
      include_regions: true,
      include_figures: includeFigures,
      include_figure_data: false,
    }, 'Searching');
    if (result) {
      setSubmittedSearchQuery(searchQuery.trim());
      setResults(result);
      if (result[0]) {
        selectSearchResult(result[0]);
      } else {
        setSelected(null);
      }
      setCenterView('search');
    }
  }

  const MAX_ATTACHMENTS = 6;

  function readFileAsDataUrl(file: File): Promise<string> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result));
      reader.onerror = () => reject(reader.error ?? new Error('Failed to read file'));
      reader.readAsDataURL(file);
    });
  }

  // Reads dropped/selected image files into data URLs and adds them as chat
  // attachments, up to MAX_ATTACHMENTS. Non-image files are ignored.
  async function addAttachmentFiles(fileList: FileList | File[]) {
    const files = Array.from(fileList).filter((file) => file.type.startsWith('image/'));
    if (!files.length) return;
    const room = MAX_ATTACHMENTS - attachments.length;
    if (room <= 0) {
      setErrorMessage(`You can attach up to ${MAX_ATTACHMENTS} images per message.`);
      return;
    }
    const accepted = files.slice(0, room);
    const read = await Promise.all(
      accepted.map(async (file) => ({
        id: `att_${Math.random().toString(36).slice(2)}`,
        name: file.name,
        mime_type: file.type,
        data_url: await readFileAsDataUrl(file),
      })),
    );
    setAttachments((prev) => [...prev, ...read]);
    if (files.length > accepted.length) {
      setErrorMessage(`Only ${room} more image(s) could be attached (limit ${MAX_ATTACHMENTS} per message).`);
    }
  }

  function removeAttachment(id: string) {
    setAttachments((prev) => prev.filter((a) => a.id !== id));
  }

  function stopAnswer() {
    const requestId = activeAnswerRequestIdRef.current;
    if (!chatBusy || !requestId) return;
    answerCanceledRef.current = true;
    void window.vera.cancelAnswer(requestId).catch((error) => {
      answerCanceledRef.current = false;
      setErrorMessage(error instanceof Error ? error.message : 'Unable to stop the answer');
    });
  }

  async function askTarget(prompt: string, onAccepted: () => void) {
    if (conversionInProgress) return;
    if (!hasSearchableScope) {
      setErrorMessage('This library does not contain any VERA documents yet.');
      return;
    }
    const provider = activeProvider;
    if (!provider) {
      setErrorMessage('Select a provider and model before asking.');
      setSettingsOpen(true);
      return;
    }
    const model = activeModel.trim();
    if (!model) {
      setErrorMessage(`Select a model for "${providerDisplayName(provider)}".`);
      setModelPickerOpen(true);
      return;
    }
    if (!provider.base_url.trim()) {
      setErrorMessage(`Set a base URL for "${providerDisplayName(provider)}" before asking.`);
      setSettingsOpen(true);
      return;
    }
    if (provider.auth_type === 'api_key' && !provider.has_api_key) {
      setErrorMessage(`Save an API key for "${providerDisplayName(provider)}" before asking with API key auth.`);
      setSettingsOpen(true);
      return;
    }
    if (await promptForIndexBeforeQuery()) return;
    const modelOptions = provider.model_options?.[model] ?? {};
    const llm: Record<string, unknown> = {
      provider: provider.provider,
      provider_key: provider.preset_key,
      model: activeModel,
      base_url: provider.base_url,
      api_key_env: provider.api_key_env,
      auth_type: provider.auth_type,
      temperature: provider.temperature,
    };
    if (modelOptions.reasoning_effort) llm.reasoning_effort = modelOptions.reasoning_effort;
    if (modelOptions.fast) llm.service_tier = 'priority';
    onAccepted();

    // Build conversation history from prior turns for multi-turn context.
    const history = sessionTurns.map((t) => ({ role: t.role, content: t.content }));

    // Carry forward citation labels so `[C#]` markers stay stable across the whole
    // session: the same chunk keeps its original id in follow-up answers, and new
    // chunks continue numbering after the highest id already used.
    const priorCitationsMap = new Map<string, { id: string; chunk_id: string }>();
    for (const t of sessionTurns) {
      if (t.role !== 'assistant' || !t.citations) continue;
      for (const c of t.citations) {
        const chunkId = c.result?.chunk_id;
        if (chunkId && !priorCitationsMap.has(chunkId)) {
          priorCitationsMap.set(chunkId, { id: c.id, chunk_id: chunkId });
        }
      }
    }
    const priorCitations = [...priorCitationsMap.values()];

    answerCanceledRef.current = false;
    const answerRequestId = crypto.randomUUID();
    activeAnswerRequestIdRef.current = answerRequestId;

    // Optimistically append the user turn to the thread.
    const pendingAttachments = attachments;
    const userTurn: SessionTurn = {
      role: 'user',
      content: prompt,
      timestamp: Date.now(),
      ...(pendingAttachments.length ? { attachments: pendingAttachments } : {}),
    };
    const nextTurns = [...sessionTurns, userTurn];
    shouldAutoScrollThreadRef.current = true;
    setShowJumpToLatest(false);
    setSessionTurns(nextTurns);
    setAttachments([]);

    // Set up streaming event listener before firing the request.
    setStreamEvents([]);
    setTraceEvents([]);
    setFailedTraceEvents([]);
    setStreamingAnswer('');
    setResponseStatus('Thinking');
    streamingAnswerRef.current = '';
    // Collect every trace event locally too, so it survives even if the backend
    // response doesn't echo a `trace` array (e.g. an older sidecar process).
    const collectedTrace: StreamEvent[] = [];
    const offEvents = window.vera.onAnswerEvent((ev) => {
      if (ev.id !== answerRequestId) return;
      collectedTrace.push(ev);
      setTraceEvents((prev) => [...prev, ev]);
      if (ev.event === 'llm_request') {
        setResponseStatus('Asking');
      } else if (ev.event === 'tool_call') {
        setResponseStatus('Retrieving');
      } else if (ev.event === 'search_start') {
        setResponseStatus('Searching');
        setStreamEvents((prev) => [...prev, ev]);
      } else if (ev.event === 'search_done') {
        setResponseStatus('Retrieving');
        setStreamEvents((prev) => {
          const revIdx = [...prev].reverse().findIndex((e) => e.event === 'search_start' && e.query === ev.query);
          if (revIdx >= 0) {
            const idx = prev.length - 1 - revIdx;
            return prev.map((e, i) => i === idx ? ev : e);
          }
          return [...prev, ev];
        });
      } else if (ev.event === 'answer_delta') {
        setResponseStatus('Thinking');
        const delta = ev.text ?? '';
        streamingAnswerRef.current += delta;
        setStreamingAnswer((prev) => prev + delta);
      } else if (ev.event === 'answer_reset') {
        streamingAnswerRef.current = '';
        setStreamingAnswer('');
      }
    });

    const result = await call<ChatAnswerResult>({
      action: 'answer',
      path: searchScopePath,
      ...(selectedFiles.length ? { paths: selectedFiles } : {}),
      ...(activeLibraryPath && selectedFiles.length === 0
        ? { recursive: activeIndexStatus?.fresh ? activeIndexStatus.recursive ?? true : true, excludes: activeIndexStatus?.excludes ?? [] }
        : {}),
      prompt,
      mode_id: activeModeId || activeMode?.id || '',
      history,
      prior_citations: priorCitations,
      llm,
      ...(pendingAttachments.length
        ? { attachments: pendingAttachments.map(({ name, mime_type, data_url }) => ({ name, mime_type, data_url })) }
        : {}),
    }, 'Asking', answerRequestId, { timeoutMs: 0 });
    offEvents();
    const wasCancelled = answerCanceledRef.current;
    const partialAnswer = streamingAnswerRef.current.trim();
    if (activeAnswerRequestIdRef.current === answerRequestId) {
      activeAnswerRequestIdRef.current = null;
    }
    setStreamEvents([]);
    setTraceEvents([]);
    setStreamingAnswer('');
    setResponseStatus('Thinking');
    streamingAnswerRef.current = '';
    if (result && !wasCancelled) {
      const now = Date.now();
      const sid = activeSessionId ?? `sess_${Math.random().toString(36).slice(2)}`;
      // Prefer the structured trace from the backend; fall back to the events we
      // captured live so the trace never vanishes once the response arrives.
      const turnTrace = result.trace?.length ? result.trace : collectedTrace;
      // Append the assistant turn.
      const assistantTurn: SessionTurn = {
        role: 'assistant',
        content: result.answer,
        citations: result.citations,
        searches: result.searches,
        ...(selectedFiles.length ? { selected_paths: selectedFiles } : {}),
        answer_mode: result.answer_mode,
        mode_label: result.mode_label,
        trace: turnTrace,
        images_sent: result.images_sent,
        vision_fallback: result.vision_fallback,
        llm: result.llm,
        timestamp: now,
      };
      // Keep the (large) trace in memory only — see traceMemory note above.
      if (turnTrace.length) {
        traceMemory.set(traceKey(sid, now), turnTrace);
      }
      const withAssistant = [...nextTurns, assistantTurn];
      setSessionTurns(withAssistant);

      // Also keep chatAnswer for citation/source pane wiring.
      setChatAnswer(result);
      const citedResults = result.citations.map((c) => c.result);
      setResults(citedResults);
      const linkableById = new Map<string, ChatCitationResult>();
      for (const turn of sessionTurns) {
        for (const citation of turn.citations ?? []) {
          linkableById.set(citation.id, citation);
        }
      }
      for (const citation of result.citations) {
        linkableById.set(citation.id, citation);
      }
      const firstAnswerCitation = firstCitationInAnswer(result.answer, linkableById.values());
      if (firstAnswerCitation) selectSearchResult(firstAnswerCitation.result);
      else setSelected(null);
      setViewerMode('document');

      // Persist / update session — strip traces so the on-disk store stays lean.
      const title = withAssistant[0]?.content.slice(0, 60) || 'New session';
      const session: Session = {
        id: sid,
        title,
        source_path: searchScopePath,
        ...(selectedFiles.length ? { selected_paths: selectedFiles } : {}),
        turns: withAssistant.map(stripTrace),
        created_at: activeSessionId ? (sessions.find((s) => s.id === sid)?.created_at ?? now) : now,
        updated_at: now,
      };
      if (!activeSessionId) setActiveSessionId(sid);
      const saved = await window.vera.saveSession(session);
      setSessions(saved);
    } else {
      if (wasCancelled) {
        const now = Date.now();
        const sid = activeSessionId ?? `sess_${Math.random().toString(36).slice(2)}`;
        const interruptedTurn: SessionTurn = {
          role: 'assistant',
          content: partialAnswer
            ? `${partialAnswer}\n\n*Generation stopped.*`
            : '*Generation stopped before a response was produced.*',
          ...(selectedFiles.length ? { selected_paths: selectedFiles } : {}),
          trace: collectedTrace,
          timestamp: now,
        };
        if (collectedTrace.length) {
          traceMemory.set(traceKey(sid, now), collectedTrace);
        }
        const withInterruptedAnswer = [...nextTurns, interruptedTurn];
        setSessionTurns(withInterruptedAnswer);
        const session: Session = {
          id: sid,
          title: withInterruptedAnswer[0]?.content.slice(0, 60) || 'New session',
          source_path: searchScopePath,
          ...(selectedFiles.length ? { selected_paths: selectedFiles } : {}),
          turns: withInterruptedAnswer.map(stripTrace),
          created_at: activeSessionId ? (sessions.find((s) => s.id === sid)?.created_at ?? now) : now,
          updated_at: now,
        };
        if (!activeSessionId) setActiveSessionId(sid);
        const saved = await window.vera.saveSession(session);
        setSessions(saved);
        return;
      }
      // Roll back optimistic user turn on failure.
      setFailedTraceEvents(collectedTrace);
      setSessionTurns(sessionTurns);
      setComposerRestoredDraft((previous) => ({ version: previous.version + 1, text: prompt }));
      setAttachments(pendingAttachments);
    }
  }

  async function newSession() {
    setChatAnswer(null);
    setSessionTurns([]);
    setActiveSessionId(null);
    setResults([]);
    setSelected(null);
    setSearchQuery('');
    setComposerResetVersion((version) => version + 1);
    setAttachments([]);
  }

  async function loadSession(session: Session) {
    setActiveSessionId(session.id);
    // Re-attach any in-memory traces captured earlier this app session.
    const hydratedTurns = session.turns.map((turn) => {
      if (turn.role !== 'assistant') return turn;
      const trace = traceMemory.get(traceKey(session.id, turn.timestamp));
      return trace ? { ...turn, trace } : turn;
    });
    shouldAutoScrollThreadRef.current = true;
    setShowJumpToLatest(false);
    setSessionTurns(hydratedTurns);
    // Restore scope before selecting citations so result.file fallbacks resolve
    // against the session path. Viewer content is replaced by loadSourceDocument below.
    const sessionPath = session.source_path;
    if (sessionPath && sessionPath !== path) {
      await openTargetPath(sessionPath);
    }
    const storedSelection = session.selected_paths ?? [];
    const availablePaths = new Set(folders.flatMap((folder) => folder.entries.map((entry) => entry.path)));
    const restoredSelection = availablePaths.size
      ? storedSelection.filter((filePath) => availablePaths.has(filePath))
      : storedSelection;
    setSelectedFiles(restoredSelection);
    if (storedSelection.length > restoredSelection.length) {
    }
    // Restore the last cited result for source pane. Use the session's path (not the
    // possibly-stale `path` closure) as the single-document fallback; corpus results
    // carry their own `file`.
    const lastAssistant = [...session.turns].reverse().find((t) => t.role === 'assistant');
    if (lastAssistant?.citations?.length) {
      const citedResults = lastAssistant.citations.map((c) => c.result);
      setResults(citedResults);
      const first = citedResults[0];
      setSelected(first);
      const resultPath = first.file || sessionPath || path;
      if (resultPath) void loadSourceDocument(resultPath, false);
    } else {
      setResults([]);
      setSelected(null);
      if (sessionPath) void loadSourceDocument(sessionPath, false);
    }
    setViewerMode('document');
  }

  async function removeSession(id: string) {
    const saved = await window.vera.deleteSession(id);
    setSessions(saved);
    if (activeSessionId === id) {
      void newSession();
    }
  }

  async function persistSettings(next: AppSettings): Promise<AppSettings> {
    const saved = await window.vera.saveSettings(next);
    setProviders(saved.providers);
    setActiveProviderId(saved.active_provider_id);
    setActiveModel(saved.active_model || '');
    setActiveModeId(saved.active_mode_id || '');
    setEmbeddingModel(saved.embedding_model || 'hashing');
    setIngestPipeline(saved.ingest_pipeline || 'pymupdf');
    setIngestPipelineConfigs(saved.ingest_pipeline_configs || {});
    setHasHfToken(Boolean(saved.has_hf_token));
    return saved;
  }

  async function refreshSettings(): Promise<AppSettings> {
    const saved = await window.vera.getSettings();
    setProviders(saved.providers);
    setActiveProviderId(saved.active_provider_id);
    setActiveModel(saved.active_model || '');
    setActiveModeId(saved.active_mode_id || '');
    setEmbeddingModel(saved.embedding_model || 'hashing');
    setIngestPipeline(saved.ingest_pipeline || 'pymupdf');
    setIngestPipelineConfigs(saved.ingest_pipeline_configs || {});
    setHasHfToken(Boolean(saved.has_hf_token));
    return saved;
  }

  function settingsSnapshot(overrides?: Partial<AppSettings>): AppSettings {
    return {
      providers,
      active_provider_id: activeProviderId,
      active_model: activeModel,
      active_mode_id: activeModeId,
      embedding_model: embeddingModel,
      ingest_pipeline: ingestPipeline,
      ingest_pipeline_configs: ingestPipelineConfigs,
      ...overrides,
    };
  }

  async function saveEmbeddingModel(model: string) {
    const nextModel = model.trim() || 'hashing';
    setEmbeddingModel(nextModel);
    await persistSettings(settingsSnapshot({ embedding_model: nextModel }));
  }

  async function saveIngestPipeline(pipeline: string) {
    const nextPipeline = pipeline.trim() || 'pymupdf';
    const nextConfigs = {
      ...ingestPipelineConfigs,
      [ingestPipeline]: pipelineOptions,
    };
    const nextDescriptor = ingestPipelineDescriptors.find(
      (item) => item.spec === nextPipeline || item.provider === nextPipeline,
    ) ?? null;
    const nextOptions = mergePipelineFieldValues(nextDescriptor, nextConfigs[nextPipeline]);
    setIngestPipeline(nextPipeline);
    setIngestPipelineConfigs(nextConfigs);
    setPipelineOptions(nextOptions);
    await persistSettings(settingsSnapshot({
      ingest_pipeline: nextPipeline,
      ingest_pipeline_configs: {
        ...nextConfigs,
        [nextPipeline]: nextOptions,
      },
    }));
  }

  async function savePipelineOptions(nextOptions: PipelineOptions) {
    setPipelineOptions(nextOptions);
    const nextConfigs = {
      ...ingestPipelineConfigs,
      [ingestPipeline]: nextOptions,
    };
    setIngestPipelineConfigs(nextConfigs);
    await persistSettings(settingsSnapshot({ ingest_pipeline_configs: nextConfigs }));
  }
  async function selectActiveModel(providerId: string, model: string) {
    setModelPickerOpen(false);
    setActiveProviderId(providerId);
    setActiveModel(model);
    await persistSettings(settingsSnapshot({
      active_provider_id: providerId,
      active_model: model,
    }));
  }

  async function refreshProviderModels(providerId: string) {
    const profile = providers.find((entry) => entry.id === providerId);
    if (!profile) return;
    if (!profile.base_url.trim()) {
      setModelRefreshMessage(`Set a base URL for ${providerDisplayName(profile)} first.`);
      return;
    }
    setModelRefreshBusyId(providerId);
    setModelRefreshMessage(`Refreshing ${providerDisplayName(profile)}…`);
    try {
      const response = await window.vera.request<{ models: string[] }>({
        action: 'list_models',
        llm: {
          provider: profile.provider,
          base_url: profile.base_url,
          api_key_env: profile.api_key_env,
          auth_type: profile.auth_type,
        },
      });
      if (!response.ok) {
        setModelRefreshMessage(response.error || 'Unable to refresh models.');
        return;
      }
      const discovered = filterDiscoveredModels(profile, response.result?.models ?? []);
      const enabled = profile.models.length ? profile.models : defaultEnabledModels(profile, discovered);
      const nextProviders = providers.map((entry) => entry.id === providerId
        ? { ...entry, available_models: discovered, models_refreshed_at: Date.now(), models: enabled }
        : entry);
      const nextActiveModel = activeProviderId === providerId && !enabled.includes(activeModel)
        ? (enabled[0] ?? '')
        : activeModel;
      await persistSettings(settingsSnapshot({
        providers: nextProviders,
        active_model: nextActiveModel,
      }));
      setModelRefreshMessage(discovered.length
        ? `Found ${discovered.length} models from ${providerDisplayName(profile)}.`
        : `${providerDisplayName(profile)} returned no models.`);
    } finally {
      setModelRefreshBusyId('');
    }
  }

  async function toggleProviderModel(providerId: string, model: string) {
    const profile = providers.find((entry) => entry.id === providerId);
    if (!profile) return;
    const enabled = profile.models.includes(model)
      ? profile.models.filter((entry) => entry !== model)
      : [...profile.models, model];
    const nextProviders = providers.map((entry) => entry.id === providerId ? { ...entry, models: enabled } : entry);
    const nextActiveModel = activeProviderId === providerId && activeModel === model && !enabled.includes(model)
      ? (enabled[0] ?? '')
      : activeModel;
    await persistSettings(settingsSnapshot({
      providers: nextProviders,
      active_model: nextActiveModel,
    }));
  }

  async function updateModelOptions(
    providerId: string,
    model: string,
    options: { reasoning_effort?: string; fast?: boolean },
  ) {
    const nextProviders = providers.map((entry) => entry.id === providerId
      ? {
          ...entry,
          model_options: {
            ...(entry.model_options ?? {}),
            [model]: options,
          },
        }
      : entry);
    await persistSettings(settingsSnapshot({ providers: nextProviders }));
  }

  useEffect(() => {
    const cycleReasoning = (event: KeyboardEvent) => {
      if (!event.ctrlKey || !event.altKey || event.code !== 'Slash' || !activeProvider || !activeModel) return;
      event.preventDefault();
      const options = activeProvider.model_options?.[activeModel] ?? {};
      const current = options.reasoning_effort && options.reasoning_effort !== 'none'
        ? options.reasoning_effort
        : 'medium';
      const currentIndex = REASONING_EFFORTS.indexOf(current as (typeof REASONING_EFFORTS)[number]);
      const next = REASONING_EFFORTS[(currentIndex + 1) % REASONING_EFFORTS.length];
      void updateModelOptions(activeProvider.id, activeModel, { ...options, reasoning_effort: next });
    };
    window.addEventListener('keydown', cycleReasoning);
    return () => window.removeEventListener('keydown', cycleReasoning);
  }, [activeProvider, activeModel, providers, activeProviderId, activeModeId]);

  async function selectActiveMode(modeId: string) {
    setModePickerOpen(false);
    setActiveModeId(modeId);
    await persistSettings(settingsSnapshot({ active_mode_id: modeId }));
  }

  function updateConversionTask(
    update: Partial<Omit<BackgroundTask, 'id' | 'kind'>>,
    requestId = conversionRequestIdRef.current,
  ) {
    if (!requestId) return;
    dispatchBackgroundTask({ type: 'update', id: requestId, update });
  }

  function stopConversion() {
    const requestId = conversionRequestIdRef.current;
    if (!conversionInProgress || !requestId) return;
    conversionCanceledRef.current = true;
    conversionInterruptRef.current = 'stop';
    updateConversionTask({ message: 'Stopping…' }, requestId);
    void window.vera.cancelAnswer(requestId).then((result) => {
      if (result && 'cancelled' in result && !result.cancelled) {
        conversionCanceledRef.current = false;
        conversionInterruptRef.current = null;
        updateConversionTask({ message: 'Converting…' }, requestId);
        setConversionError('Unable to stop conversion (request was not found). Restart the app if this persists.');
      } else if (result && 'cancelled' in result && result.cancelled) {
        clearConversionUi(requestId);
      }
    }).catch((error) => {
      conversionCanceledRef.current = false;
      conversionInterruptRef.current = null;
      updateConversionTask({ message: 'Converting…' }, requestId);
      setConversionError(error instanceof Error ? error.message : 'Unable to stop conversion');
    });
  }

  function skipCurrentConversion() {
    const requestId = conversionRequestIdRef.current;
    if (!conversionInProgress || !requestId || (convertMode !== 'batch' && convertMode !== 'selected')) return;
    if (conversionInterruptRef.current === 'stop') return;
    conversionInterruptRef.current = 'skip';
    updateConversionTask({ message: 'Skipping…' }, requestId);
    void window.vera.skipConversion(requestId).then((result) => {
      if (!result.skipped) {
        conversionInterruptRef.current = null;
        updateConversionTask({ message: 'Converting…' }, requestId);
        setConversionError('Unable to skip file (request was not found). Restart the app if this persists.');
      }
    }).catch((error) => {
      conversionInterruptRef.current = null;
      updateConversionTask({ message: 'Converting…' }, requestId);
      setConversionError(error instanceof Error ? error.message : 'Unable to skip file');
    });
  }

  function applyConversionProgress(requestId: string, event: StreamEvent, mode: 'single' | 'batch') {
    // Keep "Stopping…" visible until the request ends.
    if (conversionInterruptRef.current === 'stop') return;
    // After skip is acknowledged, the next progress event means we moved on.
    if (conversionInterruptRef.current === 'skip') {
      conversionInterruptRef.current = null;
    }
    const total = event.total ?? 0;
    const completed = event.completed ?? 0;
    const currentFile = event.input?.trim() || null;
    if (event.phase === 'discovering') {
      updateConversionTask({
        phase: event.phase,
        message: 'Discovering PDFs…',
        completed,
        total,
        currentItem: currentFile || undefined,
      }, requestId);
      return;
    }
    const update = {
      phase: event.phase,
      completed,
      total,
      currentItem: currentFile || undefined,
    };
    if (!total) {
      updateConversionTask({
        ...update,
        message: mode === 'batch' ? 'No PDFs found to convert.' : 'Converting…',
      }, requestId);
      return;
    }
    if (completed >= total) {
      updateConversionTask({
        ...update,
        message: mode === 'batch' ? `Converted ${completed} of ${total}` : 'Converted',
      }, requestId);
      return;
    }
    const current = completed + 1;
    updateConversionTask({ ...update, message: `${current} of ${total}` }, requestId);
  }

  async function refreshFoldersForPath(target: string) {
    await Promise.all(
      folders
        .filter((folder) => isPathInsideFolder(target, folder.path))
        .map((folder) => refreshFolder(folder.path, { showBusy: false })),
    );
  }

  function refreshFoldersAfterConversion(target: string) {
    void refreshFoldersForPath(target).catch((error) => {
      console.error('Unable to refresh folders after conversion', error);
    });
  }

  function clearConversionUi(requestId: string) {
    if (conversionProgressCleanupRef.current?.requestId === requestId) {
      conversionProgressCleanupRef.current.off();
      conversionProgressCleanupRef.current = null;
    }
    if (conversionRequestIdRef.current !== requestId) return;
    conversionRequestIdRef.current = null;
    dispatchBackgroundTask({ type: 'finish', id: requestId });
    conversionInterruptRef.current = null;
  }

  function settleConversionRequest(requestId: string) {
    clearConversionUi(requestId);
  }

  function conversionRequestWasSuperseded(requestId: string) {
    const activeRequestId = conversionRequestIdRef.current;
    return activeRequestId !== null && activeRequestId !== requestId;
  }

  async function batchConvertPdfs(options: { paths?: string[] } = {}) {
    const selectedPaths = (options.paths ?? []).map((entry) => entry.trim()).filter(Boolean);
    const directory = batchDirectory.trim();
    if (!selectedPaths.length && !directory) {
      setConversionError(selectedPaths.length === 0 && convertMode === 'selected'
        ? 'Select one or more PDFs in Explorer (click, Ctrl/Cmd+click, or Shift+click).'
        : 'Choose the directory containing the PDFs to convert.');
      return;
    }
    conversionCanceledRef.current = false;
    conversionInterruptRef.current = null;
    setConversionError(null);
    setBatchConvertResult(null);
    setReconvertNotice(null);
    const conversionRequestId = crypto.randomUUID();
    conversionRequestIdRef.current = conversionRequestId;
    dispatchBackgroundTask({
      type: 'start',
      task: {
        id: conversionRequestId,
        kind: 'conversion',
        label: 'Conversion',
        message: 'Starting…',
      },
    });
    const refreshRoot = selectedPaths[0] || directory;
    const offProgress = window.vera.onAnswerEvent((event) => {
      if (event.id !== conversionRequestId || event.event !== 'conversion_progress') return;
      applyConversionProgress(conversionRequestId, event, 'batch');
    });
    conversionProgressCleanupRef.current = { requestId: conversionRequestId, off: offProgress };
    try {
      const response = await awaitConversionRequest(
        window.vera.request<BatchConvertResult>({
          action: 'batch_convert',
          ...(selectedPaths.length
            ? { paths: selectedPaths }
            : { directory, recursive: batchRecursive }),
          overwrite: batchOverwrite,
          model: embeddingModel,
          parser: ingestPipeline,
          store_original: storeOriginal,
          pipeline_options: pipelineOptions,
        }, conversionRequestId),
        () => settleConversionRequest(conversionRequestId),
      );
      if (conversionRequestWasSuperseded(conversionRequestId)) return;
      if (response.cancelled || response.error?.includes('cancelled')) {
        refreshFoldersAfterConversion(refreshRoot);
        setConversionError(null);
        return;
      }
      if (!response.ok || !response.result) {
        throw new Error(response.error || (selectedPaths.length ? 'Selected PDF conversion failed' : 'PDF directory conversion failed'));
      }
      const result = response.result;
      setBatchConvertResult(result);
      refreshFoldersAfterConversion(result.directory || refreshRoot);
      if (selectedPaths.length) {
        setSelectedPdfs([]);
      }
    } catch (error) {
      if (conversionRequestWasSuperseded(conversionRequestId)) return;
      const message = error instanceof Error
        ? error.message
        : (selectedPaths.length ? 'Selected PDF conversion failed' : 'PDF directory conversion failed');
      if (conversionCanceledRef.current || message.toLowerCase().includes('cancelled')) {
        refreshFoldersAfterConversion(refreshRoot);
        setConversionError(null);
        return;
      }
      setConversionError(message);
    } finally {
      settleConversionRequest(conversionRequestId);
      if (conversionRequestIdRef.current === null) {
        conversionCanceledRef.current = false;
        conversionInterruptRef.current = null;
      }
      restoreConvertDefaultsAfterReconvert();
    }
  }

  async function loadSourceDocument(
    targetPath = path,
    activateViewer = true,
    requestId = ++sourceDocumentLoadRef.current,
  ) {
    if (folders.some((folder) => folder.path === targetPath)) {
      if (requestId === sourceDocumentLoadRef.current) {
        setPendingSourcePath('');
      }
      return;
    }
    setPendingSourcePath(targetPath);
    try {
      const result = await call<SourceDocumentResult>(
        { action: 'source', path: targetPath },
        'Loading source',
        undefined,
        { scope: 'source', timeoutMs: SOURCE_LOAD_TIMEOUT_MS },
      );
      if (result && requestId === sourceDocumentLoadRef.current) {
        setLibraryInfoPath('');
        setSourceDocument(result);
        setSourceDocumentPath(targetPath);
        if (activateViewer) setViewerMode('document');
      }
    } finally {
      if (requestId === sourceDocumentLoadRef.current) {
        setPendingSourcePath('');
      }
    }
  }

  function closeSourceDocument() {
    cancelActionScope('source');
    sourceDocumentLoadRef.current += 1;
    setSourceDocument(null);
    setSourceDocumentPath('');
    setPendingSourcePath('');
    setLibraryInfoPath('');
    setSelected(null);
    setViewerMode('document');
  }

  function selectSearchResult(result: SearchResult) {
    const resultPath = result.file || path;
    const figureRequestId = ++figureDataLoadRef.current;
    const cachedFigures: FigureResult[] = [];
    for (const figure of result.figures || []) {
      if (!figure.asset_id) continue;
      if (figure.data_url) {
        figureDataCache.current.set(
          figureCacheKey(resultPath, figure.asset_id),
          figure,
        );
        cachedFigures.push(figure);
        continue;
      }
      const cached = figureDataCache.current.get(
        figureCacheKey(resultPath, figure.asset_id),
      );
      if (cached) cachedFigures.push(cached);
    }
    const hydratedResult = mergeFigureData(result, cachedFigures);
    setSelected(hydratedResult);
    const missingAssetIds = (hydratedResult.figures || [])
      .filter((figure) => figure.asset_id && !figure.data_url)
      .map((figure) => figure.asset_id as string);
    if (resultPath && missingAssetIds.length) {
      void window.vera.request<FigureResult[]>({
        action: 'figure_data',
        path: resultPath,
        asset_ids: missingAssetIds,
      }).then((response) => {
        if (!response.ok || figureRequestId !== figureDataLoadRef.current) return;
        const loadedFigures = response.result || [];
        for (const figure of loadedFigures) {
          if (!figure.asset_id || !figure.data_url) continue;
          figureDataCache.current.set(
            figureCacheKey(resultPath, figure.asset_id),
            figure,
          );
        }
        setSelected((current) => (
          current && sameSearchResult(current, result)
            ? mergeFigureData(current, loadedFigures)
            : current
        ));
        setResults((current) => current.map((entry) => (
          sameSearchResult(entry, result)
            ? mergeFigureData(entry, loadedFigures)
            : entry
        )));
      }).catch(() => undefined);
    }
    // Every selection supersedes earlier document requests, including a click
    // back to the document that is already visible while another load is pending.
    const requestId = ++sourceDocumentLoadRef.current;
    if (resultPath && (resultPath !== sourceDocumentPath || !sourceDocument)) {
      void loadSourceDocument(resultPath, false, requestId);
    } else {
      cancelActionScope('source');
      setPendingSourcePath('');
    }
  }

  function selectChunkResult(index: number) {
    const result = results[index];
    if (!result) return;
    selectSearchResult(result);
    setCitationJumpVersion((version) => version + 1);
  }

  function selectCitation(citation: ChatCitationResult, citationGroup?: ChatCitationResult[]) {
    if (citationGroup?.length) {
      setResults(citationGroup.map((entry) => entry.result));
    }
    selectSearchResult(citation.result);
    setCitationJumpVersion((version) => version + 1);
    setViewerMode('document');
  }

  // `selectCitation` is recreated every render (it closes over lots of state), which
  // would defeat memoization on chat-turn children. Route through a ref so callers get
  // a permanently stable function identity while still always invoking the latest logic.
  const selectCitationRef = useRef(selectCitation);
  selectCitationRef.current = selectCitation;
  const stableSelectCitation = useMemo(
    () => (citation: ChatCitationResult, citationGroup?: ChatCitationResult[]) => selectCitationRef.current(citation, citationGroup),
    [],
  );

  const handleOpenTargetRef = useRef<(targetPath: string) => void>(() => {});
  handleOpenTargetRef.current = (targetPath: string) => {
    routeOpenTarget(targetPath, {
      addFolder: (folderPath) => { void addFolderFromPath(folderPath); },
      openFile: (filePath) => { void openTargetPath(filePath); },
    });
  };

  useEffect(() => window.vera.onOpenTarget((targetPath) => {
    handleOpenTargetRef.current(targetPath);
  }), []);

  useEffect(() => window.vera.onOpenSettings(() => {
    setSettingsOpen(true);
  }), []);

  const folderPathsKey = folders.map((folder) => folder.path).join('\n');

  // Keep folder headers scannable: expand the active library, collapse the rest.
  // Selecting a .vera clears the active library for Search/Ask scope but must
  // not collapse the folder the user just clicked. Manual caret toggles still
  // work until the active library or folder set changes.
  useEffect(() => {
    const folderPaths = folderPathsKey ? folderPathsKey.split('\n') : [];
    setCollapsedFolders((prev) => syncCollapsedFolders(folderPaths, activeLibraryPath, prev));
  }, [folderPathsKey, activeLibraryPath]);

  useAppBootstrap({
    applySettings: (saved) => {
      setProviders(saved.providers);
      setActiveProviderId(saved.active_provider_id);
      setActiveModel(saved.active_model || '');
      setActiveModeId(saved.active_mode_id || '');
      setEmbeddingModel(saved.embedding_model || 'hashing');
      setIngestPipeline(saved.ingest_pipeline || 'pymupdf');
      setIngestPipelineConfigs(saved.ingest_pipeline_configs || {});
      setHasHfToken(Boolean(saved.has_hf_token));
    },
    setEmbeddingProviders,
    setIngestPipelineDescriptors,
    setSessions,
    loadFolders,
  });

  useEffect(() => {
    setPageNumber(1);
    setPageResult(null);
  }, [viewerInfoPath]);

  useEffect(() => {
    if (!ingestPipelineDescriptors.length) return;
    const descriptor = ingestPipelineDescriptors.find(
      (item) => item.spec === ingestPipeline || item.provider === ingestPipeline,
    ) ?? null;
    setPipelineOptions(mergePipelineFieldValues(
      descriptor,
      ingestPipelineConfigs[ingestPipeline],
    ));
  }, [ingestPipelineDescriptors, ingestPipeline, ingestPipelineConfigs]);

  const loadModes = React.useCallback(async () => {
    const response = await window.vera.listModes();
    if (response.ok && response.result) {
      setModes(response.result.modes);
    }
  }, []);

  useEffect(() => {
    void loadModes();
  }, [loadModes]);

  // Follow streamed content only while the reader remains at the bottom. Once
  // they scroll up, preserve their position until they explicitly jump back.
  useEffect(() => {
    const thread = threadRef.current;
    if (!thread || !shouldAutoScrollThreadRef.current) return;
    thread.scrollTo({ top: thread.scrollHeight, behavior: 'auto' });
  }, [sessionTurns.length, streamingAnswer, streamEvents, traceEvents.length, showTrace]);

  function handleThreadScroll() {
    const thread = threadRef.current;
    if (!thread) return;
    const nearBottom = thread.scrollHeight - thread.scrollTop - thread.clientHeight <= 80;
    shouldAutoScrollThreadRef.current = nearBottom;
    setShowJumpToLatest(!nearBottom);
  }

  function jumpToLatest() {
    const thread = threadRef.current;
    if (!thread) return;
    shouldAutoScrollThreadRef.current = true;
    setShowJumpToLatest(false);
    thread.scrollTo({ top: thread.scrollHeight, behavior: 'auto' });
  }

  useEffect(() => {
    if (!isResizingSource) return undefined;
    function handlePointerMove(event: PointerEvent) {
      event.preventDefault();
      resizeSourcePane(event.clientX);
    }
    function handlePointerUp() {
      setIsResizingSource(false);
    }
    document.body.classList.add('resizingPanes');
    window.addEventListener('pointermove', handlePointerMove);
    window.addEventListener('pointerup', handlePointerUp);
    return () => {
      document.body.classList.remove('resizingPanes');
      window.removeEventListener('pointermove', handlePointerMove);
      window.removeEventListener('pointerup', handlePointerUp);
    };
  }, [isResizingSource]);

  useEffect(() => {
    if (!isResizingSide) return undefined;
    function handlePointerMove(event: PointerEvent) {
      event.preventDefault();
      resizeSidePanel(event.clientX);
    }
    function handlePointerUp() {
      setIsResizingSide(false);
    }
    document.body.classList.add('resizingPanes');
    window.addEventListener('pointermove', handlePointerMove);
    window.addEventListener('pointerup', handlePointerUp);
    return () => {
      document.body.classList.remove('resizingPanes');
      window.removeEventListener('pointermove', handlePointerMove);
      window.removeEventListener('pointerup', handlePointerUp);
    };
  }, [isResizingSide]);

  useEffect(() => {
    try { localStorage.setItem('vera.sidePanelWidth', String(sidePanelWidth)); } catch { /* ignore persistence errors */ }
  }, [sidePanelWidth]);

  // The sidecar only returns citations retrieved during the current request.
  // Keep prior full citation payloads available to link a follow-up answer that
  // reuses a stable `[C#]` marker without performing another search.
  const linkableCitations = useMemo(() => {
    const citationsById = new Map<string, ChatCitationResult>();
    for (const turn of sessionTurns) {
      if (turn.role !== 'assistant') continue;
      for (const citation of turn.citations ?? []) {
        if (!citationsById.has(citation.id)) citationsById.set(citation.id, citation);
      }
    }
    return [...citationsById.values()];
  }, [sessionTurns]);

  return (
    <div className={customTitlebar ? 'appShell appShell--customTitlebar' : 'appShell'}>
      {customTitlebar ? (
        <header className="appTitlebar">
          <span className="appTitlebarLogo" title="VERA"><VeraIcon size={14} /></span>
          <nav className="appMenu" aria-label="Application menu">
            {[
              ['fileMenu', 'File'],
              ['editMenu', 'Edit'],
              ['viewMenu', 'View'],
              ['helpMenu', 'Help'],
            ].map(([id, label]) => (
              <button
                type="button"
                key={id}
                onClick={(event) => {
                  const rect = event.currentTarget.getBoundingClientRect();
                  void window.vera.showMenu(id, rect.left, rect.bottom);
                }}
              >
                {label}
              </button>
            ))}
          </nav>
        </header>
      ) : null}
      <div
        className={[
          'appBody',
          sidebarCollapsed ? 'appBody--sidebarCollapsed' : '',
          viewerCollapsed ? 'appBody--viewerCollapsed' : '',
          viewerExpanded && !viewerCollapsed ? 'appBody--viewerExpanded' : '',
        ].filter(Boolean).join(' ')}
        ref={workspaceRef}
        style={{ '--source-pane-width': `${sourcePaneWidth}%`, '--side-panel-width': `${sidePanelWidth}px` } as CSSProperties}
      >
        <aside className={sidebarCollapsed ? 'sidePanel sidePanel--collapsed' : 'sidePanel'}>
          <div className="sidePanelHeader">
            <button
              type="button"
              className="ghostIcon"
              onClick={() => setSidebarCollapsed((value) => !value)}
              title={sidebarCollapsed ? 'Show sidebar' : 'Hide sidebar'}
              aria-label={sidebarCollapsed ? 'Show sidebar' : 'Hide sidebar'}
              aria-pressed={!sidebarCollapsed}
            >
              {sidebarCollapsed ? <PanelLeftOpen size={15} /> : <PanelLeftClose size={15} />}
            </button>
            {!sidebarCollapsed ? (
              <>
                <nav className="sideViewNav" aria-label="Sidebar views">
                  {([
                    ['explorer', 'Explorer', Folder],
                    ['chats', 'Chats', MessageSquareText],
                    ['convert', 'Convert PDF', FileInput],
                  ] as const).map(([view, label, Icon]) => (
                    <button
                      className={`ghostIcon sideViewButton${sideView === view ? ' active' : ''}`}
                      key={view}
                      onClick={() => openSide(view)}
                      title={label}
                      aria-label={label}
                      aria-pressed={sideView === view}
                    >
                      <Icon size={15} />
                    </button>
                  ))}
                </nav>
                <div className="sidePanelActions">
                  {sideView === 'explorer' ? (
                    <>
                      <button className="ghostIcon" onClick={() => void addFolder()} title="Open folder"><FolderOpen size={15} /></button>
                      <button className="ghostIcon" onClick={async () => { const f = await window.vera.pickArchive(); if (f) void openTargetPath(f); }} title="Open .vera file"><VeraIcon size={15} /></button>
                    </>
                  ) : null}
                  <button className="ghostIcon" onClick={() => setSettingsOpen(true)} title="LLM Providers" aria-label="LLM Providers"><Settings size={15} /></button>
                </div>
              </>
            ) : null}
          </div>
          {!sidebarCollapsed ? (
            <div
              className={`sidePanelBody${sideView === 'explorer' ? ' sidePanelBody--explorer' : ''}${sideView === 'chats' ? ' sidePanelBody--chats' : ''}`}
              tabIndex={sideView === 'explorer' ? -1 : undefined}
              onMouseDown={sideView === 'explorer' ? (event) => handleExplorerBlankPointer(event) : undefined}
            >
              {sideView === 'explorer' ? (
                <ExplorerPanel
                  folders={folders}
                  activeLibraryPath={activeLibraryPath}
                  path={path}
                  selectedFiles={selectedFiles}
                  selectedPdfs={selectedPdfs}
                  selectionAnchorPath={selectionAnchorPath}
                  explorerSelection={explorerSelection}
                  explorerFileFilter={explorerFileFilter}
                  collapsedFolders={collapsedFolders}
                  pendingSourcePath={pendingSourcePath}
                  sourceDocumentPath={sourceDocumentPath}
                  sourceLoading={sourceLoading}
                  indexStatuses={indexStatuses}
                  indexStatusChecking={indexStatusChecking}
                  indexReports={indexReports}
                  indexingFolders={indexingFolders}
                  busyFolderPath={busyFolderPath}
                  busyAction={busyAction}
                  convertLocked={convertLocked}
                  escapeBlocked={Boolean(settingsOpen || indexPrompt || indexReport)}
                  onClearFileSelection={clearExplorerFileSelection}
                  onAddFolder={() => { void addFolder(); }}
                  onFileFilterChange={setExplorerFileFilter}
                  onCollapsedFoldersChange={setCollapsedFolders}
                  onFileSelectionChange={(next) => {
                    setSelectedFiles(next.selectedFiles);
                    setSelectedPdfs(next.selectedPdfs);
                    setSelectionAnchorPath(next.selectionAnchorPath);
                    setExplorerSelection(next.explorerSelection);
                  }}
                  onSelectFolder={selectExplorerFolder}
                  onOpenLibraryInfo={(folderPath) => { void openLibraryInfo(folderPath); }}
                  onUpdateTargetPath={updateTargetPath}
                  onPreview={(entry) => { void previewSourceDocument(entry); }}
                  onShowIndexReport={(report) => {
                    setIndexPrompt(null);
                    setIndexReport(report);
                  }}
                  onConvertFolder={openConvertFolder}
                  onConvertSelected={openConvertSelected}
                  onReconvert={(entry, folderPath) => { void openReconvert(entry, folderPath); }}
                  onManageIndex={(folderPath) => { void manageLibraryIndex(folderPath); }}
                  onRefreshFolder={(folderPath) => { void refreshFolder(folderPath); }}
                  onRevealInFolder={(targetPath) => { void revealInFolder(targetPath); }}
                  onRemoveFolder={removeFolder}
                  onTrashEntry={(entry, folderPath) => { void trashEntry(entry, folderPath); }}
                />
              ) : null}

              {sideView === 'chats' ? (
                <div className="chatsView">
                  <button className="sidePrimary" onClick={() => void newSession()}><Plus size={15} />New chat</button>
                  {sessions.length === 0 ? (
                    <p className="sideMuted">No conversations yet.</p>
                  ) : (
                    sessions.map((s) => (
                      <div key={s.id} className={s.id === activeSessionId ? 'chatRow active' : 'chatRow'}>
                        <button className="chatRowTitle" onClick={() => void loadSession(s)} title={s.title}>
                          <MessageSquareText size={14} />
                          <span>{s.title}</span>
                        </button>
                        <button className="ghostIcon tiny" onClick={() => void removeSession(s.id)} title="Delete chat"><Trash2 size={12} /></button>
                      </div>
                    ))
                  )}
                </div>
              ) : null}

              {sideView === 'convert' ? (
                <ConvertPanel
                  convertMode={convertMode}
                  selectedPdfs={selectedPdfs}
                  batchDirectory={batchDirectory}
                  batchRecursive={batchRecursive}
                  batchOverwrite={batchOverwrite}
                  storeOriginal={storeOriginal}
                  embeddingModel={embeddingModel}
                  embeddingProviders={embeddingProviders}
                  ingestPipeline={ingestPipeline}
                  ingestPipelineDescriptors={ingestPipelineDescriptors}
                  pipelineOptions={pipelineOptions}
                  explorerSelection={explorerSelection}
                  activeLibraryPath={activeLibraryPath}
                  busy={busy}
                  convertLocked={convertLocked}
                  conversionInProgress={conversionInProgress}
                  reconvertBusy={reconvertBusy}
                  reconvertNotice={reconvertNotice}
                  conversionStatus={conversionStatus}
                  conversionError={conversionError}
                  batchConvertResult={batchConvertResult}
                  onConvertModeChange={setConvertMode}
                  onSelectedPdfsChange={setSelectedPdfs}
                  onBatchDirectoryChange={setBatchDirectory}
                  onBatchRecursiveChange={setBatchRecursive}
                  onBatchOverwriteChange={setBatchOverwrite}
                  onStoreOriginalChange={setStoreOriginal}
                  onEmbeddingModelChange={setEmbeddingModel}
                  onSaveEmbeddingModel={(model) => { void saveEmbeddingModel(model); }}
                  onSaveIngestPipeline={(pipeline) => { void saveIngestPipeline(pipeline); }}
                  onSavePipelineOptions={(next) => { void savePipelineOptions(next); }}
                  onChoosePdfs={() => { void choosePdfs(); }}
                  onChooseDirectory={() => { void chooseBatchDirectory(); }}
                  onToggleSelectedPdf={toggleSelectedPdf}
                  onConvert={() => {
                    if (convertMode === 'selected') void batchConvertPdfs({ paths: selectedPdfs });
                    else void batchConvertPdfs();
                  }}
                  onSkip={skipCurrentConversion}
                  onStop={stopConversion}
                />
              ) : null}

            </div>
          ) : null}
        </aside>

        {!sidebarCollapsed ? (
          <div
            className={isResizingSide ? 'paneDivider sideDivider resizing' : 'paneDivider sideDivider'}
            role="separator"
            aria-label="Resize side panel"
            aria-orientation="vertical"
            tabIndex={0}
            onDoubleClick={() => setSidePanelWidth(260)}
            onKeyDown={(event) => {
              if (event.key === 'ArrowLeft') setSidePanelWidth((value) => clampSidePanelWidth(value - 16));
              if (event.key === 'ArrowRight') setSidePanelWidth((value) => clampSidePanelWidth(value + 16));
              if (event.key === 'Home') setSidePanelWidth(200);
              if (event.key === 'End') setSidePanelWidth(600);
            }}
            onPointerDown={(event) => {
              event.preventDefault();
              setIsResizingSide(true);
              resizeSidePanel(event.clientX);
            }}
          />
        ) : null}

        {!(viewerExpanded && !viewerCollapsed) ? (
        <main className="centerPane">
          <header className="centerHeader">
            <div className="centerViewToggle" role="group" aria-label="Center workspace">
              <button
                type="button"
                className={centerView === 'chat' ? 'active' : ''}
                onClick={() => setCenterView('chat')}
                aria-pressed={centerView === 'chat'}
              >
                Chat
              </button>
              <button
                type="button"
                className={centerView === 'search' ? 'active' : ''}
                onClick={() => setCenterView('search')}
                aria-pressed={centerView === 'search'}
              >
                Search
              </button>
            </div>
            {centerView === 'chat' ? (
              <button className="centerNewChat" onClick={() => void newSession()} title="Start a new chat"><Plus size={14} />New chat</button>
            ) : null}
          </header>

          {errorMessage ? (
            <div className="errorBanner centerBanner" role="alert">
              <AlertTriangle size={15} aria-hidden="true" />
              <span className="errorBannerMessage" title={errorMessage}>{errorMessage}</span>
              {showTrace && providerErrorDetail ? (
                <details className="providerErrorDetails">
                  <summary>Provider error details</summary>
                  <pre>{providerErrorDetail}</pre>
                </details>
              ) : null}
              {showTrace && failedTraceEvents.length ? (
                <div className="failedTrace">
                  <TraceView events={failedTraceEvents} />
                </div>
              ) : null}
              <button
                type="button"
                className="errorBannerDismiss"
                aria-label="Dismiss error"
                title="Dismiss error"
                onClick={() => {
                  setErrorMessage(null);
                  setProviderErrorDetail(null);
                  setFailedTraceEvents([]);
                }}
              >
                <X size={14} />
              </button>
            </div>
          ) : null}
          {centerView === 'search' ? (
            <section className={submittedSearchQuery ? 'centerSearch centerSearch--active' : 'centerSearch centerSearch--empty'}>
              {submittedSearchQuery ? (
                <div className="searchThread">
                  <article className="chatMessage userMessage searchQueryMessage">
                    <p>{submittedSearchQuery}</p>
                  </article>
                  <article className="chatMessage assistantMessage searchResponse">
                    <span>{results.length} result{results.length === 1 ? '' : 's'}</span>
                    {results.length > 0 ? (
                      <div className="centerSearchResults">
                        {results.map((result, index) => (
                          <button
                            className={selected?.chunk_id === result.chunk_id ? 'searchResultCard active' : 'searchResultCard'}
                            key={`${result.file || result.document_id}-${result.chunk_id}`}
                            onClick={() => { selectSearchResult(result); setViewerMode('document'); }}
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
                  <span>
                    {selectedFiles.length > 0
                      ? `${selectedFiles.length} selected document${selectedFiles.length === 1 ? '' : 's'}`
                      : activeLibraryIsEmpty ? `“${fileName(activeLibraryPath)}” is empty`
                      : activeLibraryPath ? `All documents in “${fileName(activeLibraryPath)}”` : path ? `Current document: “${fileName(path)}”` : 'No search scope'}
                  </span>
                  {selectedFiles.length > 0 ? (
                    <button type="button" onClick={() => setSelectedFiles([])}>Clear</button>
                  ) : null}
                </div>
                <div className="searchComposer">
                  <textarea
                    value={searchQuery}
                    rows={1}
                    onChange={(event) => setSearchQuery(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' && !event.shiftKey) {
                        event.preventDefault();
                        if (hasSearchableScope && searchQuery.trim() && !busy) void searchTarget();
                      }
                    }}
                    placeholder="Search the active scope…"
                    aria-label="Search query"
                  />
                  <button
                    type="button"
                    className="askSendButton"
                    onClick={() => void searchTarget()}
                    disabled={!hasSearchableScope || !searchQuery.trim() || busy}
                    aria-label="Search"
                  >
                    {searchBusy ? <span className="askSpinner" /> : <Search size={14} />}
                  </button>
                </div>
                <div className="searchOptionsBar">
                  <label>
                    <span>Mode</span>
                    <select value={mode} onChange={(event) => setMode(event.target.value)}>
                      <option value="hybrid">Hybrid</option>
                      <option value="semantic">Semantic</option>
                      <option value="keyword">Keyword</option>
                    </select>
                  </label>
                  <label>
                    <span>Results</span>
                    <input type="number" min={1} max={50} value={topK} onChange={(event) => setTopK(Number(event.target.value))} />
                  </label>
                  <label>
                    <span>Context</span>
                    <input type="number" min={0} max={5} value={contextChunks} onChange={(event) => setContextChunks(Number(event.target.value))} />
                  </label>
                  <label className="searchFiguresOption">
                    <input type="checkbox" checked={includeFigures} onChange={(event) => setIncludeFigures(event.target.checked)} />
                    <span>Figures</span>
                  </label>
                </div>
              </div>
            </section>
          ) : (
          <div className={sessionTurns.length > 0 ? 'chatPanel chatPanel--active' : 'chatPanel chatPanel--empty'}>
              {sessionTurns.length > 0 ? (
                <div className="chatThreadWrap">
                  <div className="chatThread" ref={threadRef} onScroll={handleThreadScroll}>
                    {sessionTurns.map((turn, idx) => (
                      <ChatTurn
                        key={idx}
                        turn={turn}
                        linkableCitations={linkableCitations}
                        selectCitation={stableSelectCitation}
                        selectedChunkId={selected?.chunk_id}
                        showTrace={showTrace}
                      />
                    ))}
                    {chatBusy ? (
                      <article className="chatMessage assistantMessage streamingMessage">
                        <ActivityTrace
                          live
                          status={responseStatus}
                          searches={streamEvents.map((ev) => ({
                            query: ev.query || '',
                            mode: ev.mode,
                            hits: ev.hits,
                            pending: ev.event !== 'search_done',
                          }))}
                        />
                        {streamingAnswer ? (
                          <div className="markdownBody"><Markdown remarkPlugins={[remarkGfm]}>{streamingAnswer}</Markdown></div>
                        ) : null}
                        {showTrace && traceEvents.length > 0 ? <TraceView events={traceEvents} /> : null}
                      </article>
                    ) : null}
                  </div>
                  {showJumpToLatest ? (
                    <button
                      type="button"
                      className="jumpToLatest"
                      onClick={jumpToLatest}
                      aria-label="Jump to the latest chat response"
                    >
                      <ChevronDown size={15} />
                      Jump to latest
                    </button>
                  ) : null}
                </div>
              ) : null}
              <div className="askComposerWrap">
                <div className="composerScope">
                  {conversionInProgress
                    ? 'Chat unavailable while the conversion completes.'
                    : selectedFiles.length > 0
                      ? (
                        <details className="composerScopeDocuments">
                          <summary>{selectedFiles.length} selected document{selectedFiles.length === 1 ? '' : 's'}</summary>
                          <ul>
                            {selectedFiles.map((filePath) => (
                              <li key={filePath} title={filePath}>{fileName(filePath)}</li>
                            ))}
                          </ul>
                        </details>
                      )
                      : activeLibraryIsEmpty ? `“${fileName(activeLibraryPath)}” is empty`
                      : activeLibraryPath ? `All documents in “${fileName(activeLibraryPath)}”` : path ? `Current document: “${fileName(path)}”` : 'No search scope'}
                </div>
                <ChatComposer
                  attachments={attachments}
                  busy={chatBusy || conversionInProgress}
                  busyAction={busyAction}
                  hasSearchableScope={hasSearchableScope}
                  hasPreviousTurns={sessionTurns.length > 0}
                  resetVersion={composerResetVersion}
                  restoredDraft={composerRestoredDraft}
                  onAddAttachments={addAttachmentFiles}
                  onRemoveAttachment={removeAttachment}
                  onAsk={askTarget}
                  onStopAnswer={stopAnswer}
                />
                <div className="composerBar">
                    <div className="modelPicker">
                      <button
                        type="button"
                        className="modelPickerButton"
                        onClick={() => setModePickerOpen((open) => !open)}
                      >
                        <ListChecks size={14} />
                        <span>{activeMode ? activeMode.label : 'Mode'}</span>
                        <ChevronDown size={14} />
                      </button>
                      {modePickerOpen ? (
                        <>
                          <div className="modelPickerBackdrop" onClick={() => setModePickerOpen(false)} />
                          <div className="modelPickerMenu" role="menu">
                            <div className="modelPickerGroupLabel">Answer mode</div>
                            {modes.map((entry) => (
                              <button
                                type="button"
                                key={entry.id}
                                className={entry.id === (activeMode?.id ?? '') ? 'modelOption active' : 'modelOption'}
                                onClick={() => void selectActiveMode(entry.id)}
                              >
                                <span>{entry.label}{entry.builtin ? '' : ' · custom'}</span>
                                {entry.description ? <small>{entry.description}</small> : null}
                              </button>
                            ))}
                            <div className="modelPickerSep" />
                            <button
                              type="button"
                              className="modelOption manageOption"
                              onClick={() => {
                                setModePickerOpen(false);
                                void window.vera.openModesFolder();
                              }}
                            >
                              <FolderOpen size={14} />
                              <span>Open modes folder…</span>
                            </button>
                            <button
                              type="button"
                              className="modelOption manageOption"
                              onClick={() => {
                                setModePickerOpen(false);
                                void loadModes();
                              }}
                            >
                              <RefreshCw size={14} />
                              <span>Reload modes</span>
                            </button>
                          </div>
                        </>
                      ) : null}
                    </div>
                    <div className="modelPicker">
                      <button
                        type="button"
                        className="modelPickerButton"
                        title="Select model · Ctrl+Alt+/ cycles reasoning effort"
                        onClick={() => {
                          const opening = !modelPickerOpen;
                          setModelPickerOpen(opening);
                          if (!opening) return;
                          setModelFilter('');
                          const refreshedAt = activeProvider?.models_refreshed_at ?? 0;
                          if (activeProvider && Date.now() - refreshedAt > 60 * 60 * 1000) {
                            void refreshProviderModels(activeProvider.id);
                          }
                        }}
                      >
                        <span>
                          {activeProvider && activeModel
                            ? `${activeModel}${activeModelOptions.reasoning_effort ? ` · ${reasoningEffortLabel(activeModelOptions.reasoning_effort)}` : ''}${activeModelOptions.fast ? ' · Fast' : ''}`
                            : 'Select model'}
                        </span>
                        <ChevronDown size={14} />
                      </button>
                      {modelPickerOpen ? (
                        <>
                          <div className="modelPickerBackdrop" onClick={() => setModelPickerOpen(false)} />
                          <div className="modelPickerMenu" role="menu" onMouseLeave={() => setHoveredModelOptions(null)}>
                            <div className="modelPickerMenuScroll">
                              <div className="modelPickerSearch">
                                <Search size={13} />
                                <input value={modelFilter} onChange={(event) => setModelFilter(event.target.value)} placeholder="Search models" autoFocus />
                              </div>
                              {providers.length === 0 ? (
                                <div className="modelPickerEmpty">No providers yet — add one below.</div>
                              ) : null}
                              {providers.map((profile) => (
                                <div className="modelPickerGroup" key={profile.id}>
                                  <div className="modelPickerGroupLabel">{providerDisplayName(profile)}</div>
                                  {profile.models.length === 0 ? (
                                    <div className="modelPickerEmpty">No models enabled</div>
                                  ) : (
                                    profile.models
                                      .filter((model) => !modelFilter.trim() || model.toLowerCase().includes(modelFilter.trim().toLowerCase()))
                                      .map((model) => (
                                      <button
                                        type="button"
                                        key={`${profile.id}-${model}`}
                                        className={profile.id === activeProviderId && model === activeModel ? 'modelOption active' : 'modelOption'}
                                        onClick={() => void selectActiveModel(profile.id, model)}
                                        onMouseEnter={() => {
                                          setHoveredModelOptions({
                                            providerId: profile.id,
                                            model,
                                          });
                                        }}
                                      >
                                        <span>{model}</span>
                                      </button>
                                    ))
                                  )}
                                </div>
                              ))}
                            </div>
                            <div className="modelPickerSep" />
                            <button
                              type="button"
                              className="modelOption manageOption"
                              onClick={() => {
                                if (activeProviderId) void refreshProviderModels(activeProviderId);
                                else {
                                  setModelPickerOpen(false);
                                  setSettingsOpen(true);
                                }
                              }}
                              disabled={Boolean(modelRefreshBusyId)}
                            >
                              <RefreshCw size={14} className={modelRefreshBusyId ? 'spinning' : ''} />
                              <span>{modelRefreshBusyId ? 'Refreshing models…' : 'Refresh models'}</span>
                            </button>
                            <button
                              type="button"
                              className="modelOption manageOption"
                              onClick={() => {
                                setModelPickerOpen(false);
                                setModelManagerOpen(true);
                              }}
                            >
                              <Settings size={14} />
                              <span>Edit models…</span>
                            </button>
                            {hoveredModelOptions ? (() => {
                              const profile = providers.find((entry) => entry.id === hoveredModelOptions.providerId);
                              if (!profile) return null;
                              const options: { reasoning_effort?: string; fast?: boolean } = profile.model_options?.[hoveredModelOptions.model] ?? {};
                              const thinkingEnabled = options.reasoning_effort !== 'none';
                              const selectedEffort = options.reasoning_effort && options.reasoning_effort !== 'none'
                                ? options.reasoning_effort
                                : 'medium';
                              return (
                                <div className="modelOptionsFlyout">
                                  <span className="modelOptionsHeading">Options</span>
                                  <label className="modelFlyoutToggle">
                                    <span>Thinking</span>
                                    <input
                                      type="checkbox"
                                      checked={thinkingEnabled}
                                      onChange={() => void updateModelOptions(profile.id, hoveredModelOptions.model, {
                                        ...options,
                                        reasoning_effort: thinkingEnabled ? 'none' : 'medium',
                                      })}
                                    />
                                  </label>
                                  <label className="modelFlyoutToggle">
                                    <span>Fast</span>
                                    <input
                                      type="checkbox"
                                      checked={Boolean(options.fast)}
                                      onChange={() => void updateModelOptions(profile.id, hoveredModelOptions.model, {
                                        ...options,
                                        fast: !options.fast,
                                      })}
                                    />
                                  </label>
                                  <span className="modelOptionsHeading effortHeading">Effort</span>
                                  <div className="modelEffortMenu">
                                    {REASONING_EFFORTS.map((effort) => (
                                      <button
                                        type="button"
                                        key={effort}
                                        className={thinkingEnabled && selectedEffort === effort ? 'active' : ''}
                                        disabled={!thinkingEnabled}
                                        onClick={() => void updateModelOptions(profile.id, hoveredModelOptions.model, {
                                          ...options,
                                          reasoning_effort: effort,
                                        })}
                                      >
                                        <span>{reasoningEffortLabel(effort)}</span>
                                        {thinkingEnabled && selectedEffort === effort ? <CheckCircle2 size={13} /> : null}
                                      </button>
                                    ))}
                                  </div>
                                </div>
                              );
                            })() : null}
                          </div>
                        </>
                      ) : null}
                    </div>
                    <button
                      type="button"
                      className={showTrace ? 'composerToggle active' : 'composerToggle'}
                      onClick={() => setShowTrace((value) => {
                        const next = !value;
                        try { localStorage.setItem('vera.showTrace', next ? '1' : '0'); } catch { /* ignore persistence errors */ }
                        return next;
                      })}
                      title="Show the prompts, tool calls, and responses exchanged with the LLM"
                    >
                      <Terminal size={14} />
                      <span>Trace</span>
                    </button>
                  </div>
              </div>
            </div>
          )}
        </main>
        ) : null}

        {!viewerCollapsed && !viewerExpanded ? (
          <div
            className={isResizingSource ? 'paneDivider resizing' : 'paneDivider'}
            role="separator"
            aria-label="Resize Source Document pane"
            aria-orientation="vertical"
            tabIndex={0}
            onDoubleClick={() => setSourcePaneWidth(34)}
            onKeyDown={(event) => {
              if (event.key === 'ArrowLeft') setSourcePaneWidth((value) => clampSourcePaneWidth(value + 4));
              if (event.key === 'ArrowRight') setSourcePaneWidth((value) => clampSourcePaneWidth(value - 4));
              if (event.key === 'Home') setSourcePaneWidth(32);
              if (event.key === 'End') setSourcePaneWidth(70);
            }}
            onPointerDown={(event) => {
              event.preventDefault();
              setIsResizingSource(true);
              resizeSourcePane(event.clientX);
            }}
          />
        ) : null}

        <aside className={viewerCollapsed ? 'viewerPane viewerPane--collapsed' : 'viewerPane'}>
          <div className="viewerHeader">
            {!viewerCollapsed ? (
              <div className="viewerTitleGroup">
                <h2 title={viewerTitle.title || undefined}>{viewerTitle.primary}</h2>
                {viewerTitle.secondary ? (
                  <span title={viewerTitle.title || undefined}>{viewerTitle.secondary}</span>
                ) : null}
              </div>
            ) : null}
            <div className="viewerHeaderActions">
              {!viewerCollapsed && (selected || viewerInfoPath) ? (
                <div className="viewerModeToggle">
                  {!viewerInfoIsCorpus ? (
                    <button className={viewerMode === 'document' ? 'active' : ''} onClick={() => { setViewerMode('document'); if (!sourceDocument && selectedSourcePath && !pendingSourcePath) void loadSourceDocument(selectedSourcePath, false); }} title="Show document viewer">
                      <span className="viewerModeLabel viewerModeLabel--full">Viewer</span>
                      <span className="viewerModeLabel viewerModeLabel--short">View</span>
                    </button>
                  ) : null}
                  {selected ? (
                    <button className={viewerMode === 'selection' ? 'active' : ''} onClick={() => setViewerMode('selection')} title="Show chunk details">
                      Chunk
                    </button>
                  ) : null}
                  <button
                    className={viewerMode === 'info' ? 'active' : ''}
                    onClick={() => {
                      setViewerMode('info');
                      setValidation(null);
                      setExportResult(null);
                      setPageResult(null);
                      if (viewerInfoInspectable && !viewerInfoIsCorpus && !viewerInspect) {
                        void inspectTarget(viewerInfoPath);
                      }
                    }}
                    title={viewerInfoIsArchive ? 'Inspect VERA archive metadata' : viewerInfoIsCorpus ? 'Inspect library metadata' : 'Inspect document metadata'}
                  >
                    {viewerInfoIsCorpus ? (
                      <>
                        <span className="viewerModeLabel viewerModeLabel--full">Library Info</span>
                        <span className="viewerModeLabel viewerModeLabel--short">Info</span>
                      </>
                    ) : (
                      <>
                        <span className="viewerModeLabel viewerModeLabel--full">Document Info</span>
                        <span className="viewerModeLabel viewerModeLabel--short">Info</span>
                      </>
                    )}
                  </button>
                </div>
              ) : null}
              {!viewerCollapsed && (sourceDocument || libraryInfoPath || pendingSourcePath) ? (
                <button
                  type="button"
                  className="ghostIcon"
                  onClick={closeSourceDocument}
                  title={libraryInfoPath ? 'Close library info' : pendingSourcePath ? 'Cancel loading' : 'Close document'}
                  aria-label={libraryInfoPath ? 'Close library info' : pendingSourcePath ? 'Cancel loading' : 'Close document'}
                >
                  <X size={15} />
                </button>
              ) : null}
              {!viewerCollapsed ? (
                <button
                  type="button"
                  className="ghostIcon"
                  onClick={() => setViewerExpanded((value) => !value)}
                  title={viewerExpanded ? 'Show chat' : 'Expand viewer'}
                  aria-label={viewerExpanded ? 'Show chat' : 'Expand viewer'}
                  aria-pressed={viewerExpanded}
                >
                  {viewerExpanded ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
                </button>
              ) : null}
              <button
                type="button"
                className="ghostIcon"
                onClick={() => {
                  setViewerCollapsed((value) => {
                    const next = !value;
                    if (next) setViewerExpanded(false);
                    return next;
                  });
                }}
                title={viewerCollapsed ? 'Show document viewer' : 'Hide document viewer'}
                aria-label={viewerCollapsed ? 'Show document viewer' : 'Hide document viewer'}
                aria-pressed={!viewerCollapsed}
              >
                {viewerCollapsed ? <PanelRightOpen size={15} /> : <PanelRightClose size={15} />}
              </button>
            </div>
          </div>
          {!viewerCollapsed ? (
            viewerMode === 'info' ? (
              <DocumentInfoPanel
                viewerInfoPath={viewerInfoPath}
                viewerInfoIsCorpus={viewerInfoIsCorpus}
                viewerInfoIsArchive={viewerInfoIsArchive}
                viewerInfoInspectable={viewerInfoInspectable}
                viewerInspect={viewerInspect}
                viewerIndexStatus={viewerIndexStatus}
                activeLibraryIsEmpty={activeLibraryIsEmpty}
                busy={busy}
                validation={validation}
                exportResult={exportResult}
                sourceDocument={sourceDocument}
                pageNumber={pageNumber}
                pageResult={pageResult}
                call={call}
                onInspect={(target) => { void inspectTarget(target); }}
                onValidation={setValidation}
                onExportResult={setExportResult}
                onPageNumberChange={setPageNumber}
                onPageResult={setPageResult}
              />
            ) : selected && viewerMode === 'selection' ? (
              <article className="sourceDetails sourceViewerOnly">
                {results.length > 1 ? (
                  <nav className="chunkNavigator" aria-label="Chunk navigation">
                    <button
                      type="button"
                      className="chunkNavButton"
                      onClick={() => selectChunkResult(selectedChunkIndex - 1)}
                      disabled={selectedChunkIndex <= 0}
                      title="Previous chunk"
                      aria-label="Previous chunk"
                    >
                      <ChevronLeft size={15} />
                    </button>
                    <select
                      value={selectedChunkIndex >= 0 ? String(selectedChunkIndex) : ''}
                      onChange={(event) => selectChunkResult(Number(event.target.value))}
                      aria-label="Selected chunk"
                    >
                      {selectedChunkIndex < 0 ? <option value="">Select a chunk</option> : null}
                      {results.map((result, index) => {
                        const source = result.file || result.source_filename;
                        const location = `p. ${formatPages(result.page_start, result.page_end)}`;
                        const context = [
                          result.heading_path,
                          source ? fileName(source) : null,
                        ].filter(Boolean).join(' · ') || result.chunk_id;
                        return (
                          <option key={`${source || 'document'}-${result.chunk_id}-${index}`} value={index}>
                            {`${index + 1} of ${results.length} · ${location} · ${context}`}
                          </option>
                        );
                      })}
                    </select>
                    <button
                      type="button"
                      className="chunkNavButton"
                      onClick={() => selectChunkResult(selectedChunkIndex + 1)}
                      disabled={selectedChunkIndex < 0 || selectedChunkIndex >= results.length - 1}
                      title="Next chunk"
                      aria-label="Next chunk"
                    >
                      <ChevronRight size={15} />
                    </button>
                  </nav>
                ) : null}
                <details className="sourceDisclosure" open>
                  <summary>Passage Text</summary>
                  <p>{selected.text?.trim() ? selected.text : 'No passage text was returned for this citation.'}</p>
                </details>

                <details className="sourceDisclosure">
                  <summary>Metadata</summary>
                  <dl>
                    <div><dt>Chunk</dt><dd>{selected.chunk_id}</dd></div>
                    <div><dt>Heading</dt><dd>{selected.heading_path || '-'}</dd></div>
                    <div><dt>Pages</dt><dd>{formatPages(selected.page_start, selected.page_end)}</dd></div>
                    <div><dt>Regions</dt><dd>{selected.regions?.length ?? 0}</dd></div>
                    <div><dt>Figures</dt><dd>{selected.figures?.length ?? 0}</dd></div>
                  </dl>
                </details>

                {(selected.before_chunks?.length || selected.after_chunks?.length) ? (
                  <details className="sourceDisclosure">
                    <summary>Context Chunks</summary>
                    <section className="contextPanel">
                      {selected.before_chunks?.map((chunk) => (
                        <article className="contextChunk" key={`before-${chunk.chunk_id}`}>
                          <span>Before · p. {formatPages(chunk.page_start, chunk.page_end)}</span>
                          <p>{chunk.text}</p>
                        </article>
                      ))}
                      {selected.after_chunks?.map((chunk) => (
                        <article className="contextChunk" key={`after-${chunk.chunk_id}`}>
                          <span>After · p. {formatPages(chunk.page_start, chunk.page_end)}</span>
                          <p>{chunk.text}</p>
                        </article>
                      ))}
                    </section>
                  </details>
                ) : null}

                <details className="sourceDisclosure">
                  <summary>Region Coordinates</summary>
                  {selected.regions?.length ? (
                    <div className="regionList">
                      {selected.regions.map((region, index) => (
                        <div className="regionRow" key={`${region.page_number || 'page'}-${index}`}>
                          <strong>p. {region.page_number ?? '-'}</strong>
                          <span>{formatBox(region.bbox)}</span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="mutedText">No highlight regions were returned for this result.</p>
                  )}
                </details>

                <details className="sourceDisclosure">
                  <summary>Figures</summary>
                  {selected.figures?.length ? (
                    <div className="figureList">
                      {selected.figures.map((figure, index) => (
                        <article className="figureCard" key={`${figure.asset_id || figure.filename || 'figure'}-${index}`}>
                          {figure.data_url ? <img src={figure.data_url} alt={figure.caption || figure.filename || 'Figure preview'} /> : null}
                          <span>p. {figure.page_number}</span>
                          <strong>{figure.filename || figure.asset_id || 'Figure'}</strong>
                          <p>{figure.caption || 'No caption available'}</p>
                        </article>
                      ))}
                    </div>
                  ) : (
                    <p className="mutedText">No nearby figures were returned for this result.</p>
                  )}
                </details>
              </article>
            ) : pendingSourcePath && (
              !sourceDocument
              || sourceDocumentPath.replace(/\\/g, '/').toLowerCase()
                !== pendingSourcePath.replace(/\\/g, '/').toLowerCase()
            ) ? (
              <div className="emptyState emptyState--loading" role="status" aria-live="polite">
                <RefreshCw size={30} className="spinning" aria-hidden="true" />
                <strong>{fileName(pendingSourcePath)}</strong>
                <p>Loading document…</p>
              </div>
            ) : sourceDocument && isPdfSource(sourceDocument) ? (
              <div className="sourceViewer">
                <PdfSourceViewer
                  source={sourceDocument}
                  highlightRegions={viewerHighlights.regions}
                  highlightFigures={viewerHighlights.figures}
                  targetPage={viewerHighlights.targetPage}
                  jumpVersion={citationJumpVersion}
                />
              </div>
            ) : sourceDocument ? (
              <div className="unsupportedSource">
                <strong>{sourceDocument.filename}</strong>
                <span>{sourceDocument.mime_type}</span>
              </div>
            ) : (
              <div className="emptyState">
                <VeraIcon size={30} />
                <p>Select a citation or open a document to preview it here.</p>
              </div>
            )
          ) : null}
        </aside>
      </div>
      <AppStatusBar
        tasks={backgroundTasks}
        busyFolderPath={busyFolderPath}
      />
      {modelManagerOpen ? (
        <ModelManager
          providers={providers}
          busyProviderId={modelRefreshBusyId}
          message={modelRefreshMessage}
          onToggle={(providerId, model) => void toggleProviderModel(providerId, model)}
          onRefresh={(providerId) => void refreshProviderModels(providerId)}
          onAddProvider={() => {
            setModelManagerOpen(false);
            setSettingsOpen(true);
          }}
          onClose={() => setModelManagerOpen(false)}
        />
      ) : null}
      {settingsOpen ? (
        <ProviderManager
          providers={providers}
          activeProviderId={activeProviderId}
          activeModel={activeModel}
          activeModeId={activeModeId}
          embeddingModel={embeddingModel}
          ingestPipeline={ingestPipeline}
          ingestPipelineConfigs={ingestPipelineConfigs}
          hasHfToken={hasHfToken}
          onPersist={persistSettings}
          onRefresh={refreshSettings}
          onClose={() => setSettingsOpen(false)}
        />
      ) : null}
      <LibraryIndexModal
        prompt={indexPrompt}
        report={indexReport}
        recursive={indexRecursive}
        excludes={indexExcludes}
        suppressPrompt={suppressIndexPrompt}
        onRecursiveChange={setIndexRecursive}
        onExcludesChange={setIndexExcludes}
        onSuppressPromptChange={setSuppressIndexPrompt}
        onConfirm={() => void confirmIndexAction()}
        onDismiss={dismissIndexPrompt}
      />
    </div>
  );
}

createRoot(document.getElementById('root')!).render(<App />);
