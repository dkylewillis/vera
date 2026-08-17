import React, { useEffect, useLayoutEffect, useMemo, useReducer, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  FolderOpen,
  Maximize2,
  Minimize2,
  PanelRightClose,
  PanelRightOpen,
  RefreshCw,
  X,
} from 'lucide-react';
import { TraceView } from './components/activity/TraceView';
import { AppShell } from './components/AppShell';
import type { CenterView, SideView } from './components/AppShell';
import { AppStatusBar } from './components/AppStatusBar';
import { CenterChatView } from './components/CenterChatView';
import { CenterSearchView } from './components/CenterSearchView';
import { ChatsSidebar } from './components/ChatsSidebar';
import { ConvertPanel } from './components/ConvertPanel';
import { DocumentInfoPanel } from './components/DocumentInfoPanel';
import { ExplorerPanel } from './components/ExplorerPanel';
import { LibraryIndexModal, type IndexPrompt } from './components/LibraryIndexModal';
import { PdfSourceViewer } from './components/PdfSourceViewer';
import { ModelManager, SettingsModal } from './components/ProviderManagers';
import { embedderAsPipelineDescriptor } from './components/EmbedderConfigForm';
import { mergePipelineFieldValues } from './components/PipelineConfigForm';
import { VeraIcon } from './components/VeraIcon';
import { useAppBootstrap } from './hooks/useAppBootstrap';
import { useConversion } from './hooks/useConversion';
import { useSearch } from './hooks/useSearch';
import { useSidecarCall } from './hooks/useSidecarCall';
import { useSourceDocument, type ViewerMode } from './hooks/useSourceDocument';
import { useWorkspaceFolders } from './hooks/useWorkspaceFolders';
import { firstCitationInAnswer } from './lib/citations';
import { backgroundTasksReducer } from './lib/backgroundTasks';
import { EMPTY_FIGURES, EMPTY_REGIONS } from './lib/constants';
import {
  fileName,
  formatBox,
  formatPages,
  isPathInsideFolder,
  isPdfSource,
  sameFsPath,
  showInFolderLabel,
  type ExplorerSelection,
} from './lib/formatting';
import {
  INDEX_STATUSES_STORAGE_KEY,
  readSavedActiveLibraryPath,
  readSavedFolderPaths,
} from './lib/workspaceFolders';
import {
  isExplorerBlankPointerTarget,
  routeOpenTarget,
  syncCollapsedFolders,
  type ExplorerFileFilter,
} from './lib/explorer';
import { embeddingProviderFromSpec } from './lib/convertPresets';
import { libraryQueryScope } from './lib/search';
import { hydrateSessionTurns, stripTrace, traceKey } from './lib/sessions';
import { defaultEnabledModels, filterDiscoveredModels, providerDisplayName, REASONING_EFFORTS } from './lib/providers';
import { SIDECAR_ACTIONS } from '../shared/protocol';
import type { AppSettings, BatchConvertResult, ChatAnswerResult, ChatAttachment, ChatCitationResult, EmbedderDescriptor, ExportResult, FolderEntry, InspectResult, LibraryIndexBuildReport, LibraryIndexStatus, Mode, PageResult, PipelineDescriptor, PipelineOptions, ProviderProfile, SearchResult, Session, SessionTurn, SkippedSemanticModelGroup, StreamEvent, SourceDocumentResult, ValidateResult } from './types';
import './styles.css';

// In-memory store for LLM traces. Traces are large (full prompt/response dumps),
// so we keep them only for the lifetime of this app window instead of writing them
// to the on-disk session store. They survive switching between sessions but are
// discarded when the app is closed (window reload). Keyed by `${sessionId}:${turnTimestamp}`.
const traceMemory = new Map<string, StreamEvent[]>();

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
  const [embeddingDescriptors, setEmbeddingDescriptors] = useState<EmbedderDescriptor[]>([]);
  const [ingestPipeline, setIngestPipeline] = useState('pymupdf');
  const [ingestPipelineDescriptors, setIngestPipelineDescriptors] = useState<PipelineDescriptor[]>([]);
  const [ingestPipelineConfigs, setIngestPipelineConfigs] = useState<Record<string, PipelineOptions>>({});
  const [embedderConfigs, setEmbedderConfigs] = useState<Record<string, PipelineOptions>>({});
  const [pipelineOptions, setPipelineOptions] = useState<PipelineOptions>({});
  const [embedderOptions, setEmbedderOptions] = useState<PipelineOptions>({});
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
  const [exportResult, setExportResult] = useState<ExportResult | null>(null);
  const [sourceDocument, setSourceDocument] = useState<SourceDocumentResult | null>(null);
  const [sourceDocumentPath, setSourceDocumentPath] = useState('');
  const [pendingSourcePath, setPendingSourcePath] = useState('');
  const [libraryInfoPath, setLibraryInfoPath] = useState('');
  const inspectGenerationRef = useRef(0);
  const sourceLoading = Boolean(pendingSourcePath);
  const [pageNumber, setPageNumber] = useState(1);
  const [pageResult, setPageResult] = useState<PageResult | null>(null);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [skippedSemanticModelGroups, setSkippedSemanticModelGroups] = useState<SkippedSemanticModelGroup[]>([]);
  const [selected, setSelected] = useState<SearchResult | null>(null);
  const [citationJumpVersion, setCitationJumpVersion] = useState(0);
  const [selectedFiles, setSelectedFiles] = useState<string[]>([]);
  const [selectionAnchorPath, setSelectionAnchorPath] = useState<string | null>(null);
  const [collapsedFolders, setCollapsedFolders] = useState(() => (
    syncCollapsedFolders(readSavedFolderPaths(), readSavedActiveLibraryPath())
  ));
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
  const openTargetPathRef = useRef<(
    value: string,
    options?: { asLibrary?: boolean; preserveLibrary?: boolean },
  ) => Promise<void>>(async () => undefined);
  const promptForIndexBeforeQueryRef = useRef<() => Promise<boolean>>(async () => false);
  const invalidateSourceLoadRef = useRef<() => void>(() => undefined);
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
        invalidateSourceLoadRef.current();
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

  const conversion = useConversion({
    convertMode,
    selectedPdfs,
    batchDirectory,
    batchRecursive,
    batchOverwrite,
    storeOriginal,
    embeddingModel,
    ingestPipeline,
    pipelineOptions,
    embedderOptions,
    explorerSelection,
    activeLibraryPath,
    conversionInProgress,
    folders,
    ingestPipelineDescriptors,
    ingestPipelineConfigs,
    call,
    dispatchBackgroundTask,
    refreshFolder,
    setBatchDirectory,
    setBatchOverwrite,
    setStoreOriginal,
    setConvertMode,
    setSideView,
    setSidebarCollapsed,
    setReconvertNotice,
    setReconvertBusy,
    setConversionError,
    setBatchConvertResult,
    setSelectedPdfs,
    setExplorerSelection,
    setEmbeddingModel,
    setIngestPipeline,
    setIngestPipelineConfigs,
    setPipelineOptions,
  });
  const source = useSourceDocument({
    path,
    folders,
    pendingSourcePath,
    sourceDocument,
    sourceDocumentPath,
    call,
    cancelActionScope,
    openTargetPath: (value, options) => openTargetPathRef.current(value, options),
    applyConvertDefaultsFromSelection: conversion.applyConvertDefaultsFromSelection,
    setPendingSourcePath,
    setLibraryInfoPath,
    setSourceDocument,
    setSourceDocumentPath,
    setViewerMode,
    setViewerCollapsed,
    setExplorerSelection,
    setSelected,
  });
  const search = useSearch({
    hasSearchableScope,
    searchScopePath,
    selectedFiles,
    activeLibraryPath,
    activeIndexStatus,
    searchQuery,
    mode,
    topK,
    contextChunks,
    includeFigures,
    path,
    sourceDocument,
    sourceDocumentPath,
    results,
    call,
    cancelActionScope,
    promptForIndexBeforeQuery: () => promptForIndexBeforeQueryRef.current(),
    loadSourceDocument: source.loadSourceDocument,
    nextSourceLoadId: source.nextLoadId,
    setErrorMessage,
    setSubmittedSearchQuery,
    setResults,
    setSkippedSemanticModelGroups,
    setSelected,
    setCenterView,
    setCitationJumpVersion,
    setViewerMode,
    setPendingSourcePath,
  });
  const {
    applyConvertDefaultsFromSelection,
    restoreConvertDefaultsAfterReconvert,
    openConvertSelected,
    openConvertFolder,
    openReconvert,
    toggleSelectedPdf,
    choosePdfs,
    chooseBatchDirectory,
    stopConversion,
    skipCurrentConversion,
    batchConvertPdfs,
  } = conversion;
  const { loadSourceDocument, closeSourceDocument, previewSourceDocument } = source;
  const { searchTarget, selectSearchResult, selectChunkResult, selectCitation } = search;

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
    source.invalidateLoad();
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
      action: SIDECAR_ACTIONS.inspect,
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
        action: SIDECAR_ACTIONS.indexStatus,
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

    if (activeLibraryPath) {
      setExplorerSelection({ kind: 'folder', path: activeLibraryPath });
      if (path !== activeLibraryPath) setPath(activeLibraryPath);
      return true;
    }

    if (explorerSelection?.kind === 'file') {
      setExplorerSelection(null);
    }
    return true;
  }

  function handleExplorerBlankPointer(event: { button?: number; currentTarget: HTMLElement; target: EventTarget | null }) {
    if (event.button !== undefined && event.button !== 0) return;
    if (!isExplorerBlankPointerTarget(event.target, event.currentTarget)) return;
    event.currentTarget.focus({ preventScroll: true });
    clearExplorerFileSelection();
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
        source.invalidateLoad();
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
      setSelectedPdfs([]);
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
      setSelectedPdfs([]);
      setSelectionAnchorPath(null);
    }
    const generation = ++inspectGenerationRef.current;
    updateTargetPath(value);
    const result = await call<InspectResult>({ action: SIDECAR_ACTIONS.inspect, path: value }, 'Opening');
    if (result && generation === inspectGenerationRef.current) {
      setInspect(result);
      setValidation(null);
    }
  }

  openLibraryRef.current = (folderPath) => openTargetPath(folderPath, { asLibrary: true });
  openTargetPathRef.current = openTargetPath;
  promptForIndexBeforeQueryRef.current = promptForIndexBeforeQuery;
  invalidateSourceLoadRef.current = source.invalidateLoad;
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
        action: SIDECAR_ACTIONS.inspect,
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
          action: SIDECAR_ACTIONS.inspect,
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
      action: SIDECAR_ACTIONS.answer,
      path: searchScopePath,
      ...(selectedFiles.length ? { paths: selectedFiles } : {}),
      ...libraryQueryScope(activeLibraryPath, selectedFiles, activeIndexStatus),
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
    const hydratedTurns = hydrateSessionTurns(session.turns, traceMemory, session.id);
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
    setEmbedderConfigs(saved.embedder_configs || {});
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
    setEmbedderConfigs(saved.embedder_configs || {});
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
      embedder_configs: embedderConfigs,
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

  async function saveEmbedderOptions(nextOptions: PipelineOptions) {
    const provider = embeddingProviderFromSpec(embeddingModel);
    setEmbedderOptions(nextOptions);
    const nextConfigs = {
      ...embedderConfigs,
      [provider]: nextOptions,
    };
    setEmbedderConfigs(nextConfigs);
    await persistSettings(settingsSnapshot({ embedder_configs: nextConfigs }));
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
        action: SIDECAR_ACTIONS.listModels,
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

  const stableSelectCitation = selectCitation;

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
  // work until the active library or folder set changes. Layout effect applies
  // the collapse before paint so startup and library switches do not flash
  // every folder expanded.
  useLayoutEffect(() => {
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
      setEmbedderConfigs(saved.embedder_configs || {});
      setHasHfToken(Boolean(saved.has_hf_token));
    },
    setEmbeddingProviders,
    setEmbeddingDescriptors,
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

  useEffect(() => {
    if (!embeddingDescriptors.length) return;
    const provider = embeddingProviderFromSpec(embeddingModel);
    const descriptor = embeddingDescriptors.find((item) => item.provider === provider) ?? null;
    setEmbedderOptions(mergePipelineFieldValues(
      embedderAsPipelineDescriptor(descriptor),
      embedderConfigs[provider],
    ));
  }, [embeddingDescriptors, embeddingModel, embedderConfigs]);

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
      <AppShell
        workspaceRef={workspaceRef}
        sidebarCollapsed={sidebarCollapsed}
        viewerCollapsed={viewerCollapsed}
        viewerExpanded={viewerExpanded}
        sourcePaneWidth={sourcePaneWidth}
        sidePanelWidth={sidePanelWidth}
        sideView={sideView}
        centerView={centerView}
        isResizingSide={isResizingSide}
        isResizingSource={isResizingSource}
        headerActions={sideView === 'explorer' ? (
          <>
            <button className="ghostIcon" onClick={() => void addFolder()} title="Open folder"><FolderOpen size={15} /></button>
            <button className="ghostIcon" onClick={async () => { const f = await window.vera.pickArchive(); if (f) void openTargetPath(f); }} title="Open .vera file"><VeraIcon size={15} /></button>
          </>
        ) : null}
        sidebarBody={(
          <>
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
              <ChatsSidebar
                sessions={sessions}
                activeSessionId={activeSessionId}
                onNewSession={() => { void newSession(); }}
                onLoadSession={(session) => { void loadSession(session); }}
                onRemoveSession={(id) => { void removeSession(id); }}
              />
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
                  embeddingDescriptors={embeddingDescriptors}
                  embedderOptions={embedderOptions}
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
                  onSaveEmbedderOptions={(next) => { void saveEmbedderOptions(next); }}
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
          </>
        )}
        onToggleSidebar={() => setSidebarCollapsed((value) => !value)}
        onSideViewChange={(view) => openSide(view)}
        onOpenSettings={() => setSettingsOpen(true)}
        onExplorerBlankPointer={handleExplorerBlankPointer}
        onResizeSide={(clientX) => { setIsResizingSide(true); resizeSidePanel(clientX); }}
        onResetSideWidth={() => setSidePanelWidth(260)}
        onNudgeSideWidth={(delta, edge) => {
          if (edge === 'min') setSidePanelWidth(200);
          else if (edge === 'max') setSidePanelWidth(600);
          else setSidePanelWidth((value) => clampSidePanelWidth(value + delta));
        }}
        onCenterViewChange={setCenterView}
        onNewChat={() => { void newSession(); }}
        errorBanner={errorMessage ? (
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
        centerBody={centerView === 'search' ? (
          <CenterSearchView
            submittedSearchQuery={submittedSearchQuery}
            results={results}
            selected={selected}
            searchQuery={searchQuery}
            mode={mode}
            topK={topK}
            contextChunks={contextChunks}
            includeFigures={includeFigures}
            skippedSemanticModelGroups={skippedSemanticModelGroups}
            selectedFilesCount={selectedFiles.length}
            scopeLabel={
              selectedFiles.length > 0
                ? `${selectedFiles.length} selected document${selectedFiles.length === 1 ? '' : 's'}`
                : activeLibraryIsEmpty ? `“${fileName(activeLibraryPath)}” is empty`
                : activeLibraryPath ? `All documents in “${fileName(activeLibraryPath)}”` : path ? `Current document: “${fileName(path)}”` : 'No search scope'
            }
            hasSearchableScope={hasSearchableScope}
            busy={busy}
            searchBusy={searchBusy}
            onSelectResult={(result) => { selectSearchResult(result); setViewerMode('document'); }}
            onSearchQueryChange={setSearchQuery}
            onSearch={() => { void searchTarget(); }}
            onClearSelectedFiles={() => { clearExplorerFileSelection(); }}
            onModeChange={setMode}
            onTopKChange={setTopK}
            onContextChunksChange={setContextChunks}
            onIncludeFiguresChange={setIncludeFigures}
          />
        ) : (
          <CenterChatView
            sessionTurns={sessionTurns}
            linkableCitations={linkableCitations}
            selectCitation={stableSelectCitation}
            selected={selected}
            showTrace={showTrace}
            chatBusy={chatBusy}
            responseStatus={responseStatus}
            streamEvents={streamEvents}
            streamingAnswer={streamingAnswer}
            traceEvents={traceEvents}
            threadRef={threadRef}
            showJumpToLatest={showJumpToLatest}
            onThreadScroll={handleThreadScroll}
            onJumpToLatest={jumpToLatest}
            conversionInProgress={conversionInProgress}
            selectedFiles={selectedFiles}
            activeLibraryIsEmpty={activeLibraryIsEmpty}
            activeLibraryPath={activeLibraryPath}
            path={path}
            attachments={attachments}
            busyAction={busyAction}
            hasSearchableScope={hasSearchableScope}
            composerResetVersion={composerResetVersion}
            composerRestoredDraft={composerRestoredDraft}
            onAddAttachments={addAttachmentFiles}
            onRemoveAttachment={removeAttachment}
            onAsk={askTarget}
            onStopAnswer={stopAnswer}
            modePickerOpen={modePickerOpen}
            onModePickerOpenChange={setModePickerOpen}
            modes={modes}
            activeMode={activeMode}
            onSelectActiveMode={(id) => { void selectActiveMode(id); }}
            onOpenModesFolder={() => { void window.vera.openModesFolder(); }}
            onReloadModes={() => { void loadModes(); }}
            modelPickerOpen={modelPickerOpen}
            onModelPickerOpenChange={setModelPickerOpen}
            activeProvider={activeProvider}
            activeProviderId={activeProviderId}
            activeModel={activeModel}
            activeModelOptions={activeModelOptions}
            modelFilter={modelFilter}
            onModelFilterChange={setModelFilter}
            providers={providers}
            hoveredModelOptions={hoveredModelOptions}
            onHoveredModelOptionsChange={setHoveredModelOptions}
            onSelectActiveModel={(providerId, model) => { void selectActiveModel(providerId, model); }}
            onRefreshProviderModels={(providerId) => { void refreshProviderModels(providerId); }}
            modelRefreshBusyId={modelRefreshBusyId}
            onOpenSettings={() => setSettingsOpen(true)}
            onOpenModelManager={() => setModelManagerOpen(true)}
            onUpdateModelOptions={(providerId, model, options) => { void updateModelOptions(providerId, model, options); }}
            onShowTraceChange={setShowTrace}
          />
        )}
        onResizeSource={(clientX) => { setIsResizingSource(true); resizeSourcePane(clientX); }}
        onResetSourceWidth={() => setSourcePaneWidth(34)}
        onNudgeSourceWidth={(delta, edge) => {
          if (edge === 'min') setSourcePaneWidth(32);
          else if (edge === 'max') setSourcePaneWidth(70);
          else setSourcePaneWidth((value) => clampSourcePaneWidth(value + delta));
        }}
        viewer={(
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
        )}
      />

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
        <SettingsModal
          providers={providers}
          activeProviderId={activeProviderId}
          activeModel={activeModel}
          activeModeId={activeModeId}
          embeddingModel={embeddingModel}
          ingestPipeline={ingestPipeline}
          ingestPipelineConfigs={ingestPipelineConfigs}
          embedderConfigs={embedderConfigs}
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
