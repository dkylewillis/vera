import React, { type CSSProperties, useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Download,
  Database,
  FileInput,
  FileText,
  Folder,
  FolderOpen,
  Info,
  ListChecks,
  Maximize2,
  MessageSquareText,
  Minimize2,
  PanelLeftClose,
  Plus,
  RefreshCw,
  Search,
  Settings,
  ShieldCheck,
  SkipForward,
  Square,
  Terminal,
  Trash2,
  X,
} from 'lucide-react';
import { ActivityTrace } from './components/activity/ActivityTrace';
import { TraceView } from './components/activity/TraceView';
import { ChatComposer } from './components/ChatComposer';
import { ChatTurn } from './components/ChatTurn';
import { LibraryIndexModal, type IndexPrompt } from './components/LibraryIndexModal';
import { PdfSourceViewer } from './components/PdfSourceViewer';
import { ModelManager, ProviderManager } from './components/ProviderManagers';
import { VeraIcon } from './components/VeraIcon';
import { EMPTY_FIGURES, EMPTY_REGIONS } from './lib/constants';
import { defaultVeraPath, formatBox, formatPages, isPathInsideFolder, isPdfSource } from './lib/formatting';
import { filterDiscoveredModels, providerDisplayName, REASONING_EFFORTS, reasoningEffortLabel } from './lib/providers';
import type { AppSettings, BatchConvertResult, ChatAnswerResult, ChatAttachment, ChatCitationResult, ConvertResult, ExportResult, FolderEntry, InspectResult, LibraryIndexBuildReport, LibraryIndexStatus, Mode, PageResult, ProviderProfile, SearchResult, Session, SessionTurn, StreamEvent, SourceDocumentResult, ValidateResult, WorkspaceFolderResult } from './types';
import './styles.css';

type SideView = 'explorer' | 'chats' | 'search' | 'convert' | 'info';
type FolderContextMenu = { path: string; x: number; y: number };
type EntryContextMenu = { entry: FolderEntry; folderPath: string; x: number; y: number };
type ExplorerFileFilter = 'all' | FolderEntry['type'];

// In-memory store for LLM traces. Traces are large (full prompt/response dumps),
// so we keep them only for the lifetime of this app window instead of writing them
// to the on-disk session store. They survive switching between sessions but are
// discarded when the app is closed (window reload). Keyed by `${sessionId}:${turnTimestamp}`.
const traceMemory = new Map<string, StreamEvent[]>();

function traceKey(sessionId: string, timestamp: number): string {
  return `${sessionId}:${timestamp}`;
}

function fileName(filePath: string): string {
  return filePath.split(/[\\/]/).pop() || filePath;
}

function stripTrace(turn: SessionTurn): SessionTurn {
  if (!turn.trace) return turn;
  const { trace: _trace, ...rest } = turn;
  return rest;
}

function App() {
  const customTitlebar = Boolean(window.vera.platform && window.vera.platform !== 'darwin');
  const workspaceRef = useRef<HTMLDivElement | null>(null);
  const [sideView, setSideView] = useState<SideView>('explorer');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [folders, setFolders] = useState<WorkspaceFolderResult[]>([]);
  const [viewerMode, setViewerMode] = useState<'selection' | 'document'>('document');
  const [path, setPath] = useState('');
  const [activeLibraryPath, setActiveLibraryPath] = useState('');
  const [indexStatuses, setIndexStatuses] = useState<Record<string, LibraryIndexStatus>>({});
  const [indexStatusChecking, setIndexStatusChecking] = useState<Record<string, boolean>>({});
  const [indexingFolders, setIndexingFolders] = useState<Record<string, 'build' | 'update'>>({});
  const [indexReports, setIndexReports] = useState<Record<string, LibraryIndexBuildReport>>({});
  const [folderContextMenu, setFolderContextMenu] = useState<FolderContextMenu | null>(null);
  const folderContextMenuFirstActionRef = useRef<HTMLButtonElement | null>(null);
  const folderContextMenuTriggerRef = useRef<HTMLElement | null>(null);
  const [entryContextMenu, setEntryContextMenu] = useState<EntryContextMenu | null>(null);
  const entryContextMenuActionRef = useRef<HTMLButtonElement | null>(null);
  const entryContextMenuTriggerRef = useRef<HTMLElement | null>(null);
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
  const [pdfPath, setPdfPath] = useState('');
  const [outputPath, setOutputPath] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
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
  const [convertMode, setConvertMode] = useState<'single' | 'batch'>('single');
  const [batchDirectory, setBatchDirectory] = useState('');
  const [batchRecursive, setBatchRecursive] = useState(true);
  const [batchOverwrite, setBatchOverwrite] = useState(false);
  const [chunkSize, setChunkSize] = useState(500);
  const [overlap, setOverlap] = useState(75);
  const [storeOriginal, setStoreOriginal] = useState(true);
  const [status, setStatus] = useState('Ready');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [providerErrorDetail, setProviderErrorDetail] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [busyFolderPath, setBusyFolderPath] = useState('');
  const [inspect, setInspect] = useState<InspectResult | null>(null);
  const libraryInspectCache = useRef(new Map<string, InspectResult>());
  const [validation, setValidation] = useState<ValidateResult | null>(null);
  const [convertResult, setConvertResult] = useState<ConvertResult | null>(null);
  const [batchConvertResult, setBatchConvertResult] = useState<BatchConvertResult | null>(null);
  const [conversionInProgress, setConversionInProgress] = useState(false);
  const [conversionStatus, setConversionStatus] = useState<string | null>(null);
  const [conversionCurrentFile, setConversionCurrentFile] = useState<string | null>(null);
  const [conversionError, setConversionError] = useState<string | null>(null);
  const conversionRequestIdRef = useRef<string | null>(null);
  const conversionCanceledRef = useRef(false);
  const conversionInterruptRef = useRef<'stop' | 'skip' | null>(null);
  const [exportResult, setExportResult] = useState<ExportResult | null>(null);
  const [sourceDocument, setSourceDocument] = useState<SourceDocumentResult | null>(null);
  const [sourceDocumentPath, setSourceDocumentPath] = useState('');
  const [pageNumber, setPageNumber] = useState(1);
  const [pageResult, setPageResult] = useState<PageResult | null>(null);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [selected, setSelected] = useState<SearchResult | null>(null);
  const [selectedFiles, setSelectedFiles] = useState<string[]>([]);
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

  useEffect(() => {
    if (!folderContextMenu) return;
    folderContextMenuFirstActionRef.current?.focus();

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setFolderContextMenu(null);
        folderContextMenuTriggerRef.current?.focus();
        return;
      }
      if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return;

      const menu = document.querySelector('.folderContextMenu');
      const actions = [...(menu?.querySelectorAll<HTMLButtonElement>('button') ?? [])];
      if (actions.length === 0) return;
      event.preventDefault();
      const current = document.activeElement;
      const currentIndex = actions.indexOf(current as HTMLButtonElement);
      const nextIndex = event.key === 'Home'
        ? 0
        : event.key === 'End'
          ? actions.length - 1
          : (currentIndex + (event.key === 'ArrowDown' ? 1 : -1) + actions.length) % actions.length;
      actions[nextIndex].focus();
    }

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [folderContextMenu]);

  useEffect(() => {
    if (!entryContextMenu) return;
    entryContextMenuActionRef.current?.focus();

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key !== 'Escape') return;
      setEntryContextMenu(null);
      entryContextMenuTriggerRef.current?.focus();
    }

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [entryContextMenu]);
  const threadRef = useRef<HTMLDivElement | null>(null);
  const shouldAutoScrollThreadRef = useRef(true);
  const [showJumpToLatest, setShowJumpToLatest] = useState(false);
  const [sourcePaneWidth, setSourcePaneWidth] = useState(34);
  const [viewerCollapsed, setViewerCollapsed] = useState(false);
  const [isResizingSource, setIsResizingSource] = useState(false);
  const [sidePanelWidth, setSidePanelWidth] = useState(() => {
    const stored = Number(localStorage.getItem('vera.sidePanelWidth'));
    if (stored === 300) return 260;
    return stored >= 200 && stored <= 600 ? stored : 260;
  });
  const [isResizingSide, setIsResizingSide] = useState(false);

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
  const busy = Boolean(busyAction);
  const chatBusy = busyAction === 'Asking';
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

  const selectedSourcePath = selected?.file || path;
  const selectedTargetPage = selected?.regions?.find((region) => region.page_number)?.page_number ?? selected?.page_start ?? null;
  // Keep these props referentially stable so PdfSourceViewer's memoization can
  // isolate its DOM-heavy PDF tree from chat-composer keystrokes.
  const viewerHighlights = useMemo(() => {
    if (!selected || sourceDocumentPath !== selectedSourcePath) {
      return { regions: EMPTY_REGIONS, figures: EMPTY_FIGURES, targetPage: null };
    }
    return {
      regions: selected.regions || EMPTY_REGIONS,
      figures: selected.figures?.filter((figure) => figure.included_in_context) || EMPTY_FIGURES,
      targetPage: selectedTargetPage,
    };
  }, [selected, selectedSourcePath, selectedTargetPage, sourceDocumentPath]);
  const sourceExpanded = sourcePaneWidth >= 58;

  function openSide(view: SideView) {
    setSideView(view);
    setSidebarCollapsed(false);
  }

  function indexStateKey(value: LibraryIndexStatus): string {
    return `${value.exists}:${value.fresh}:${value.reasons.join('|')}`;
  }

  function presentIndexPrompt(folderPath: string, value: LibraryIndexStatus, force = false) {
    if (value.fresh || indexingFolders[folderPath]) return;
    const key = indexStateKey(value);
    if (!force && (suppressedIndexPrompts.current.has(folderPath) || dismissedIndexStates.current.get(folderPath) === key)) return;
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

  async function refreshIndexStatus(folderPath: string): Promise<LibraryIndexStatus | null> {
    setIndexStatusChecking((prev) => ({ ...prev, [folderPath]: true }));
    try {
      const response = await window.vera.request<LibraryIndexStatus>({
        action: 'index_status',
        path: folderPath,
        verify_hashes: false,
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

  async function addFolder() {
    const dir = await window.vera.pickFolder();
    if (!dir) return;
    const folder = await window.vera.listFolder(dir);
    if (!folder) return;
    setFolders((prev) => {
      const next = [...prev.filter((entry) => entry.path !== folder.path), folder];
      localStorage.setItem('vera.folders', JSON.stringify(next.map((entry) => entry.path)));
      return next;
    });
    await openTargetPath(folder.path, { asLibrary: true });
  }

  function removeFolder(folderPath: string) {
    libraryInspectCache.current.delete(folderPath);
    setFolders((prev) => {
      const next = prev.filter((entry) => entry.path !== folderPath);
      localStorage.setItem('vera.folders', JSON.stringify(next.map((entry) => entry.path)));
      return next;
    });
    if (activeLibraryPath === folderPath) {
      setActiveLibraryPath('');
      try { localStorage.removeItem('vera.activeLibraryPath'); } catch { /* ignore persistence errors */ }
      setSelectedFiles([]);
    }
    setIndexStatuses((prev) => {
      const next = { ...prev };
      delete next[folderPath];
      try {
        localStorage.setItem('vera.indexStatuses', JSON.stringify(next));
      } catch {
        // Index-state caching only improves startup feedback.
      }
      return next;
    });
  }

  async function refreshFolder(folderPath: string) {
    libraryInspectCache.current.delete(folderPath);
    setBusyFolderPath(folderPath);
    try {
      const folder = await window.vera.listFolder(folderPath);
      if (folder) setFolders((prev) => prev.map((entry) => (entry.path === folderPath ? folder : entry)));
      await refreshIndexStatus(folderPath);
      if (activeLibraryPath === folderPath && path === folderPath) {
        setInspect(null);
      }
    } finally {
      setBusyFolderPath('');
    }
  }

  function toggleSelectedFile(filePath: string) {
    setSelectedFiles((prev) =>
      prev.includes(filePath) ? prev.filter((p) => p !== filePath) : [...prev, filePath],
    );
  }

  function toggleFolderCollapsed(folderPath: string) {
    setCollapsedFolders((prev) =>
      prev.includes(folderPath) ? prev.filter((p) => p !== folderPath) : [...prev, folderPath],
    );
  }

  function showFolderContextMenu(folderPath: string, x: number, y: number) {
    folderContextMenuTriggerRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setFolderContextMenu({
      path: folderPath,
      x: Math.max(8, Math.min(x, window.innerWidth - 190)),
      y: Math.max(8, Math.min(y, window.innerHeight - 180)),
    });
  }

  function showEntryContextMenu(entry: FolderEntry, folderPath: string, x: number, y: number) {
    entryContextMenuTriggerRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setEntryContextMenu({
      entry,
      folderPath,
      x: Math.max(8, Math.min(x, window.innerWidth - 210)),
      y: Math.max(8, Math.min(y, window.innerHeight - 80)),
    });
  }

  function openEntry(entry: FolderEntry) {
    if (entry.type === 'vera') {
      // Selecting a document sets the active scope for the chat and search UI.
      // Metadata inspection is deferred until the user opens the Info panel.
      updateTargetPath(entry.path);
    } else {
      setPdfPath(entry.path);
      if (!outputPath.trim()) setOutputPath(defaultVeraPath(entry.path));
      openSide('convert');
    }
  }

  async function previewSourceDocument(entry: FolderEntry) {
    if (entry.type !== 'vera') return;
    setSelected(null);
    setViewerMode('document');
    setViewerCollapsed(false);
    await openTargetPath(entry.path, { preserveLibrary: true });
    await loadSourceDocument(entry.path);
  }

  async function trashEntry(entry: FolderEntry, folderPath: string) {
    try {
      const result = await window.vera.trashWorkspaceFile(entry.path, folderPath);
      if (result === 'cancelled') return;
      setSelectedFiles((files) => files.filter((file) => file !== entry.path));
      if (path === entry.path) updateTargetPath(activeLibraryPath || '');
      await refreshFolder(folderPath);
      setStatus(result === 'trashed'
        ? `Moved ${entry.name} to the Recycle Bin`
        : `Permanently deleted ${entry.name}`);
    } catch (error) {
      setStatus('Unable to move file to the Recycle Bin');
      setErrorMessage(error instanceof Error ? error.message : 'Unable to move file to the Recycle Bin');
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

  async function call<T>(
    payload: Record<string, unknown>,
    label: string,
    requestId?: string,
  ): Promise<T | null> {
    setStatus(label);
    setBusyAction(label);
    setErrorMessage(null);
    setProviderErrorDetail(null);
    try {
      const response = await window.vera.request<T>(payload, requestId);
      if (!response.ok) {
        if (response.cancelled || response.error?.includes('Answer cancelled')) {
          setStatus('Stopped');
          return null;
        }
        setStatus('Ready');
        setErrorMessage(response.error || 'Request failed');
        setProviderErrorDetail(response.provider_error_detail || null);
        return null;
      }
      setStatus('Ready');
      return (response.result || null) as T | null;
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Request failed';
      if (message.includes('Answer cancelled')) {
        setStatus('Stopped');
        return null;
      }
      setStatus('Ready');
      setErrorMessage(message);
      setProviderErrorDetail(null);
      return null;
    } finally {
      setBusyAction(null);
    }
  }

  async function openTargetPath(
    value: string,
    options: { asLibrary?: boolean; preserveLibrary?: boolean } = {},
  ) {
    const asLibrary = options.asLibrary ?? (
      folders.some((folder) => folder.path === value) || !value.toLowerCase().endsWith('.vera')
    );
    if (asLibrary) {
      setActiveLibraryPath(value);
      try { localStorage.setItem('vera.activeLibraryPath', value); } catch { /* ignore persistence errors */ }
      setSelectedFiles([]);
      setPath(value);
      setValidation(null);
      setExportResult(null);
      setSourceDocument(null);
      setSourceDocumentPath('');
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
    updateTargetPath(value);
    const result = await call<InspectResult>({ action: 'inspect', path: value }, 'Opening');
    if (result) {
      setInspect(result);
      setValidation(null);
    }
  }

  function updateTargetPath(value: string) {
    setPath(value);
    setInspect(null);
    setValidation(null);
    setExportResult(null);
    setSourceDocument(null);
    setSourceDocumentPath('');
    setPageResult(null);
  }

  async function choosePdf() {
    const chosen = await window.vera.pickPdf();
    if (chosen) {
      setPdfPath(chosen);
      if (!outputPath.trim()) setOutputPath(defaultVeraPath(chosen));
    }
  }

  async function chooseBatchDirectory() {
    const chosen = await window.vera.pickFolder();
    if (chosen) {
      setBatchDirectory(chosen);
      setBatchConvertResult(null);
    }
  }

  async function chooseOutput() {
    const chosen = await window.vera.saveVera(outputPath.trim() || defaultVeraPath(pdfPath));
    if (chosen) setOutputPath(chosen);
  }

  async function inspectTarget() {
    const result = await call<InspectResult>({
      action: 'inspect',
      path,
      ...(path === activeLibraryPath ? { recursive: activeIndexStatus?.recursive ?? true, excludes: activeIndexStatus?.excludes ?? [] } : {}),
    }, 'Inspecting');
    if (result) {
      if (result.directory) libraryInspectCache.current.set(path, result);
      setInspect(result);
      setValidation(null);
      openSide('info');
    }
  }

  async function validateTarget() {
    const result = await call<ValidateResult>({ action: 'validate', path }, 'Validating');
    if (result) {
      setValidation(result);
      openSide('info');
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

  async function manageLibraryIndex(folderPath: string) {
    if (indexingFolders[folderPath]) {
      setStatus('Library indexing is already in progress');
      return;
    }
    const value = indexStatuses[folderPath] ?? await refreshIndexStatus(folderPath);
    if (value) presentIndexPrompt(folderPath, value, true);
  }

  async function confirmIndexAction() {
    if (!indexPrompt) return;
    const folderPath = indexPrompt.path;
    if (indexingFolders[folderPath]) return;
    const action = indexPrompt.status.exists ? 'index_update' : 'index_build';
    const actionLabel = action === 'index_build' ? 'Building' : 'Updating';
    const excludes = indexExcludes.split(/\r?\n/).map((value) => value.trim()).filter(Boolean);
    setIndexPrompt(null);
    setIndexReport(null);
    setIndexReports((prev) => {
      const next = { ...prev };
      delete next[folderPath];
      return next;
    });
    setIndexingFolders((prev) => ({ ...prev, [folderPath]: action === 'index_build' ? 'build' : 'update' }));
    setStatus(`${actionLabel} library index in the background`);
    setErrorMessage(null);
    try {
      const response = await window.vera.request<LibraryIndexBuildReport>({
        action,
        path: folderPath,
        ...(action === 'index_build'
          ? {
              recursive: indexRecursive,
              excludes,
            }
          : {}),
      });
      if (!response.ok || !response.result) {
        throw new Error(response.error || 'Library indexing failed');
      }
      const result = response.result;
      dismissedIndexStates.current.delete(folderPath);
      setIndexReports((prev) => ({ ...prev, [folderPath]: result }));
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
        setInspect((current) => (
          current?.directory === folderPath || current?.file === folderPath ? inspected : current
        ));
      }
      setStatus(
        result.skipped
          ? `Library index ready · ${result.skipped} skipped · select the index badge for details`
          : `Library index ready · ${result.indexed} archives · ${result.chunks.toLocaleString()} chunks`,
      );
    } catch (error) {
      setStatus('Library indexing failed');
      setErrorMessage(error instanceof Error ? error.message : 'Library indexing failed');
    } finally {
      setIndexingFolders((prev) => {
        const next = { ...prev };
        delete next[folderPath];
        return next;
      });
    }
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
      include_figure_data: includeFigures,
    }, 'Searching');
    if (result) {
      setResults(result);
      if (result[0]) {
        selectSearchResult(result[0]);
      } else {
        setSelected(null);
      }
      openSide('search');
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
    if (busyAction !== 'Asking' || !requestId) return;
    answerCanceledRef.current = true;
    setStatus('Stopping…');
    void window.vera.cancelAnswer(requestId).catch((error) => {
      answerCanceledRef.current = false;
      setStatus('Ready');
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
      setStatus('Choose an LLM provider');
      setErrorMessage('Select a provider and model before asking.');
      setSettingsOpen(true);
      return;
    }
    const model = activeModel.trim();
    if (!model) {
      setStatus('Choose an LLM model');
      setErrorMessage(`Select a model for "${providerDisplayName(provider)}".`);
      setModelPickerOpen(true);
      return;
    }
    if (!provider.base_url.trim()) {
      setStatus('Choose an LLM base URL');
      setErrorMessage(`Set a base URL for "${providerDisplayName(provider)}" before asking.`);
      setSettingsOpen(true);
      return;
    }
    if (provider.auth_type === 'api_key' && !provider.has_api_key) {
      setStatus('Save an API key');
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
    }, 'Asking', answerRequestId);
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
      if (citedResults[0]) selectSearchResult(citedResults[0]);
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
    // Restore the source document FIRST so any stale source is cleared before we
    // select a cited result. Selecting first would race with openTargetPath, which
    // resets sourceDocument to null and blanks the viewer.
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
      setStatus(`Restored ${restoredSelection.length} selected document${restoredSelection.length === 1 ? '' : 's'}; ${storedSelection.length - restoredSelection.length} unavailable`);
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
    setViewerMode('selection');
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
    return saved;
  }

  async function refreshSettings(): Promise<AppSettings> {
    const saved = await window.vera.getSettings();
    setProviders(saved.providers);
    setActiveProviderId(saved.active_provider_id);
    setActiveModel(saved.active_model || '');
    setActiveModeId(saved.active_mode_id || '');
    return saved;
  }

  async function selectActiveModel(providerId: string, model: string) {
    setModelPickerOpen(false);
    setActiveProviderId(providerId);
    setActiveModel(model);
    await persistSettings({ providers, active_provider_id: providerId, active_model: model, active_mode_id: activeModeId });
  }

  async function refreshProviderModels(providerId: string) {
    const profile = providers.find((entry) => entry.id === providerId);
    if (!profile) return;
    if (!profile.base_url.trim()) {
      setModelRefreshMessage(`Set a base URL for ${providerDisplayName(profile)} first.`);
      setStatus('Set provider base URL');
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
        setStatus('Model refresh failed');
        return;
      }
      const discovered = filterDiscoveredModels(profile, response.result?.models ?? []);
      const enabled = profile.models.length ? profile.models : discovered;
      const nextProviders = providers.map((entry) => entry.id === providerId
        ? { ...entry, available_models: discovered, models_refreshed_at: Date.now(), models: enabled }
        : entry);
      const nextActiveModel = activeProviderId === providerId && !enabled.includes(activeModel)
        ? (enabled[0] ?? '')
        : activeModel;
      await persistSettings({
        providers: nextProviders,
        active_provider_id: activeProviderId,
        active_model: nextActiveModel,
        active_mode_id: activeModeId,
      });
      setModelRefreshMessage(discovered.length
        ? `Found ${discovered.length} models from ${providerDisplayName(profile)}.`
        : `${providerDisplayName(profile)} returned no models.`);
      setStatus(discovered.length ? `Found ${discovered.length} models` : 'No models returned');
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
    await persistSettings({
      providers: nextProviders,
      active_provider_id: activeProviderId,
      active_model: nextActiveModel,
      active_mode_id: activeModeId,
    });
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
    await persistSettings({
      providers: nextProviders,
      active_provider_id: activeProviderId,
      active_model: activeModel,
      active_mode_id: activeModeId,
    });
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
      setStatus(`Reasoning: ${reasoningEffortLabel(next)}`);
      void updateModelOptions(activeProvider.id, activeModel, { ...options, reasoning_effort: next });
    };
    window.addEventListener('keydown', cycleReasoning);
    return () => window.removeEventListener('keydown', cycleReasoning);
  }, [activeProvider, activeModel, providers, activeProviderId, activeModeId]);

  async function selectActiveMode(modeId: string) {
    setModePickerOpen(false);
    setActiveModeId(modeId);
    await persistSettings({ providers, active_provider_id: activeProviderId, active_model: activeModel, active_mode_id: modeId });
  }

  function stopConversion() {
    const requestId = conversionRequestIdRef.current;
    if (!conversionInProgress || !requestId) return;
    conversionCanceledRef.current = true;
    conversionInterruptRef.current = 'stop';
    setConversionStatus('Stopping…');
    void window.vera.cancelAnswer(requestId).then((result) => {
      if (result && 'cancelled' in result && !result.cancelled) {
        conversionCanceledRef.current = false;
        conversionInterruptRef.current = null;
        setConversionStatus('Converting…');
        setConversionError('Unable to stop conversion (request was not found). Restart the app if this persists.');
      }
    }).catch((error) => {
      conversionCanceledRef.current = false;
      conversionInterruptRef.current = null;
      setConversionStatus('Converting…');
      setConversionError(error instanceof Error ? error.message : 'Unable to stop conversion');
    });
  }

  function skipCurrentConversion() {
    const requestId = conversionRequestIdRef.current;
    if (!conversionInProgress || !requestId || convertMode !== 'batch') return;
    if (conversionInterruptRef.current === 'stop') return;
    conversionInterruptRef.current = 'skip';
    setConversionStatus('Skipping…');
    void window.vera.skipConversion(requestId).then((result) => {
      if (!result.skipped) {
        conversionInterruptRef.current = null;
        setConversionStatus('Converting…');
        setConversionError('Unable to skip file (request was not found). Restart the app if this persists.');
      }
    }).catch((error) => {
      conversionInterruptRef.current = null;
      setConversionStatus('Converting…');
      setConversionError(error instanceof Error ? error.message : 'Unable to skip file');
    });
  }

  function applyConversionProgress(event: StreamEvent, mode: 'single' | 'batch') {
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
      setConversionStatus('Discovering PDFs…');
      if (currentFile) setConversionCurrentFile(currentFile);
      return;
    }
    if (currentFile) setConversionCurrentFile(currentFile);
    if (!total) {
      setConversionStatus(mode === 'batch' ? 'No PDFs found to convert.' : 'Converting…');
      return;
    }
    if (completed >= total) {
      setConversionStatus(mode === 'batch' ? `Converted ${completed} of ${total}` : 'Converted');
      return;
    }
    const current = completed + 1;
    setConversionStatus(`${current} of ${total}`);
  }

  async function refreshFoldersForPath(target: string) {
    await Promise.all(
      folders
        .filter((folder) => isPathInsideFolder(target, folder.path))
        .map((folder) => refreshFolder(folder.path)),
    );
  }

  async function convertPdf() {
    const output = outputPath.trim() || defaultVeraPath(pdfPath);
    if (!output) {
      setConversionError('Choose an output path.');
      return;
    }
    setOutputPath(output);
    conversionCanceledRef.current = false;
    conversionInterruptRef.current = null;
    setConversionInProgress(true);
    setConversionStatus('Starting…');
    setConversionCurrentFile(pdfPath.trim() || null);
    setConversionError(null);
    setConvertResult(null);
    const conversionRequestId = crypto.randomUUID();
    conversionRequestIdRef.current = conversionRequestId;
    const offProgress = window.vera.onAnswerEvent((event) => {
      if (event.id !== conversionRequestId || event.event !== 'conversion_progress') return;
      applyConversionProgress(event, 'single');
    });
    try {
      const response = await window.vera.request<ConvertResult>({
        action: 'convert',
        input: pdfPath,
        output,
        model: 'hashing',
        parser: 'pymupdf',
        chunk_size: chunkSize,
        overlap,
        store_original: storeOriginal,
      }, conversionRequestId);
      if (response.cancelled || response.error?.includes('cancelled')) {
        await refreshFoldersForPath(output);
        setConversionError(null);
        return;
      }
      if (!response.ok || !response.result) {
        throw new Error(response.error || 'PDF conversion failed');
      }
      const result = response.result;
      setConvertResult(result);
      await refreshFoldersForPath(result.output);
      updateTargetPath(result.output);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'PDF conversion failed';
      if (conversionCanceledRef.current || message.toLowerCase().includes('cancelled')) {
        await refreshFoldersForPath(output);
        setConversionError(null);
        return;
      }
      setConversionError(message);
    } finally {
      offProgress();
      if (conversionRequestIdRef.current === conversionRequestId) {
        conversionRequestIdRef.current = null;
      }
      setConversionInProgress(false);
      setConversionStatus(null);
      setConversionCurrentFile(null);
      conversionCanceledRef.current = false;
      conversionInterruptRef.current = null;
    }
  }

  async function batchConvertPdfs() {
    const directory = batchDirectory.trim();
    if (!directory) {
      setConversionError('Choose the directory containing the PDFs to convert.');
      return;
    }
    conversionCanceledRef.current = false;
    conversionInterruptRef.current = null;
    setConversionInProgress(true);
    setConversionStatus('Starting…');
    setConversionCurrentFile(null);
    setConversionError(null);
    setBatchConvertResult(null);
    const conversionRequestId = crypto.randomUUID();
    conversionRequestIdRef.current = conversionRequestId;
    const offProgress = window.vera.onAnswerEvent((event) => {
      if (event.id !== conversionRequestId || event.event !== 'conversion_progress') return;
      applyConversionProgress(event, 'batch');
    });
    try {
      const response = await window.vera.request<BatchConvertResult>({
        action: 'batch_convert',
        directory,
        recursive: batchRecursive,
        overwrite: batchOverwrite,
        model: 'hashing',
        parser: 'pymupdf',
        chunk_size: chunkSize,
        overlap,
        store_original: storeOriginal,
      }, conversionRequestId);
      if (response.cancelled || response.error?.includes('cancelled')) {
        await refreshFoldersForPath(directory);
        setConversionError(null);
        return;
      }
      if (!response.ok || !response.result) {
        throw new Error(response.error || 'PDF directory conversion failed');
      }
      const result = response.result;
      setBatchConvertResult(result);
      setConvertResult(null);
      await refreshFoldersForPath(result.directory);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'PDF directory conversion failed';
      if (conversionCanceledRef.current || message.toLowerCase().includes('cancelled')) {
        await refreshFoldersForPath(directory);
        setConversionError(null);
        return;
      }
      setConversionError(message);
    } finally {
      offProgress();
      if (conversionRequestIdRef.current === conversionRequestId) {
        conversionRequestIdRef.current = null;
      }
      setConversionInProgress(false);
      setConversionStatus(null);
      setConversionCurrentFile(null);
      conversionCanceledRef.current = false;
      conversionInterruptRef.current = null;
    }
  }

  async function exportSource() {
    const output = await window.vera.saveAny();
    if (!output) return;
    const result = await call<ExportResult>({ action: 'export', path, output }, 'Exporting source');
    if (result) setExportResult(result);
  }

  async function loadSourceDocument(targetPath = path, activateViewer = true) {
    const result = await call<SourceDocumentResult>({ action: 'source', path: targetPath }, 'Loading source');
    if (result) {
      setSourceDocument(result);
      setSourceDocumentPath(targetPath);
      if (activateViewer) setViewerMode('document');
    }
  }

  function selectSearchResult(result: SearchResult) {
    setSelected(result);
    const resultPath = result.file || path;
    if (resultPath && (resultPath !== sourceDocumentPath || !sourceDocument)) {
      void loadSourceDocument(resultPath, false);
    }
  }

  function selectCitation(citation: ChatCitationResult) {
    selectSearchResult(citation.result);
    setViewerMode('document');
  }

  // `selectCitation` is recreated every render (it closes over lots of state), which
  // would defeat memoization on chat-turn children. Route through a ref so callers get
  // a permanently stable function identity while still always invoking the latest logic.
  const selectCitationRef = useRef(selectCitation);
  selectCitationRef.current = selectCitation;
  const stableSelectCitation = useMemo(() => (citation: ChatCitationResult) => selectCitationRef.current(citation), []);

  async function loadPage() {
    const result = await call<PageResult>({ action: 'page', path, page_number: pageNumber }, 'Loading page');
    if (result) {
      setPageResult(result);
      openSide('info');
    }
  }

  useEffect(() => window.vera.onOpenTarget((targetPath) => {
    void openTargetPath(targetPath);
  }), []);

  useEffect(() => window.vera.onOpenSettings(() => {
    setSettingsOpen(true);
  }), []);

  const folderPathsKey = folders.map((folder) => folder.path).join('\n');

  useEffect(() => {
    const folderPaths = folderPathsKey ? folderPathsKey.split('\n') : [];
    void window.vera.setWatchedFolders(folderPaths);
  }, [folderPathsKey]);

  useEffect(() => window.vera.onFolderChanged((folderPath) => {
    dismissedIndexStates.current.delete(folderPath);
    void window.vera.listFolder(folderPath).then((folder) => {
      if (!folder) return;
      setFolders((prev) => prev.map((entry) => (entry.path === folder.path ? folder : entry)));
    });
    void refreshIndexStatus(folderPath);
  }), []);

  useEffect(() => {
    let canceled = false;
    async function loadSettings() {
      const saved = await window.vera.getSettings();
      if (canceled) return;
      setProviders(saved.providers);
      setActiveProviderId(saved.active_provider_id);
      setActiveModel(saved.active_model || '');
      setActiveModeId(saved.active_mode_id || '');
    }
    async function loadSessions() {
      const saved = await window.vera.getSessions();
      if (canceled) return;
      setSessions(saved);
    }
    async function loadFolders() {
      let saved: string[] = [];
      try {
        saved = JSON.parse(localStorage.getItem('vera.folders') || '[]') as string[];
      } catch {
        saved = [];
      }
      if (!Array.isArray(saved) || saved.length === 0) return;
      const loaded = await Promise.all(saved.map((dir) => window.vera.listFolder(dir)));
      if (canceled) return;
      const available = loaded.filter((entry): entry is WorkspaceFolderResult => entry !== null);
      try {
        const cached = JSON.parse(localStorage.getItem('vera.indexStatuses') || '{}') as Record<string, LibraryIndexStatus>;
        if (cached && typeof cached === 'object') {
          const availablePaths = new Set(available.map((entry) => entry.path));
          setIndexStatuses(
            Object.fromEntries(
              Object.entries(cached).filter(([folderPath, status]) => (
                availablePaths.has(folderPath)
                && status
                && typeof status === 'object'
                && typeof status.exists === 'boolean'
                && typeof status.fresh === 'boolean'
                && Array.isArray(status.reasons)
              )),
            ),
          );
        }
      } catch {
        // A missing or outdated cache is safe to ignore.
      }
      setFolders(available);
      const savedActive = localStorage.getItem('vera.activeLibraryPath') || '';
      await Promise.all(
        available
          .filter((entry) => entry.path !== savedActive)
          .map((entry) => refreshIndexStatus(entry.path)),
      );
      if (!canceled && available.some((entry) => entry.path === savedActive)) {
        await openTargetPath(savedActive, { asLibrary: true });
      }
    }
    void loadSettings();
    void loadSessions();
    void loadFolders();
    return () => {
      canceled = true;
    };
  }, []);

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
      <div className={`appBody${viewerCollapsed ? ' appBody--viewerCollapsed' : ''}`} ref={workspaceRef} style={{ '--source-pane-width': `${sourcePaneWidth}%`, '--side-panel-width': `${sidePanelWidth}px` } as CSSProperties}>
        {!sidebarCollapsed ? (
          <aside className="sidePanel">
            <div className="sidePanelHeader">
              <nav className="sideViewNav" aria-label="Sidebar views">
                {([
                  ['explorer', 'Explorer', Folder],
                  ['chats', 'Chats', MessageSquareText],
                  ['search', 'Search', Search],
                  ['convert', 'Convert PDF', FileInput],
                  ['info', 'Document info', Info],
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
                <button className="ghostIcon" onClick={() => setSidebarCollapsed(true)} title="Hide sidebar"><PanelLeftClose size={15} /></button>
              </div>
            </div>
            <div className={`sidePanelBody${sideView === 'explorer' ? ' sidePanelBody--explorer' : ''}${sideView === 'chats' ? ' sidePanelBody--chats' : ''}`}>
              {sideView === 'explorer' ? (
                folders.length === 0 ? (
                  <div className="sideEmpty">
                    <Folder size={28} />
                    <p>No folders open yet.</p>
                    <button className="sidePrimary" onClick={() => void addFolder()}><FolderOpen size={15} />Open Folder</button>
                  </div>
                ) : (
                  <>
                    <div className="explorerFileFilter" role="group" aria-label="Filter explorer files">
                      {([
                        ['all', 'All'],
                        ['vera', 'VERA'],
                        ['pdf', 'PDFs'],
                      ] as const).map(([filter, label]) => (
                        <button
                          type="button"
                          key={filter}
                          className={explorerFileFilter === filter ? 'active' : ''}
                          onClick={() => setExplorerFileFilter(filter)}
                          aria-pressed={explorerFileFilter === filter}
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                    <div className="explorerTree">
                      {folders.map((folder) => {
                      const visibleEntries = explorerFileFilter === 'all'
                        ? folder.entries
                        : folder.entries.filter((entry) => entry.type === explorerFileFilter);
                      const folderIndex = indexStatuses[folder.path];
                      const folderIndexChecking = Boolean(indexStatusChecking[folder.path]);
                      const folderBusy = busyFolderPath === folder.path;
                      const folderIndexing = indexingFolders[folder.path];
                      const folderIndexReport = indexReports[folder.path];
                      const indexBadgeClass = folderIndexing
                        ? 'indexing'
                        : folderIndexChecking && !folderIndex
                          ? 'checking'
                        : folderIndexReport?.skipped
                          ? 'warning'
                          : folderIndex?.fresh
                            ? 'fresh'
                            : folderIndex?.exists ? 'stale' : 'missing';
                      const indexBadgeTitle = folderIndexing
                        ? `${folderIndexing === 'build' ? 'Building' : 'Updating'} library index in the background`
                        : folderIndexChecking && !folderIndex
                          ? 'Checking index status…'
                        : folderIndexReport?.skipped
                          ? `Indexed with ${folderIndexReport.skipped} skipped archive(s). Select for details.`
                          : folderIndex?.fresh
                            ? `${folderIndexReport ? 'Indexed. Select for the latest build report.' : 'Indexed'}${folderIndexChecking ? ' Verifying current folder state…' : ''}`
                            : folderIndex?.exists
                              ? `Index needs updating: ${folderIndex.reasons.join('; ')}${folderIndexChecking ? ' Verifying current folder state…' : ''}`
                              : 'No index';
                      return (
                      <section
                        className={activeLibraryPath === folder.path
                          ? selectedFiles.length > 0 ? 'folderGroup' : 'folderGroup activeLibrary'
                          : 'folderGroup'}
                        key={folder.path}
                      >
                        <div
                          className="folderGroupHead"
                          title={folder.path}
                          onContextMenu={(event) => {
                            event.preventDefault();
                            showFolderContextMenu(folder.path, event.clientX, event.clientY);
                          }}
                        >
                          <button
                            className="folderCollapseAction"
                            onClick={() => toggleFolderCollapsed(folder.path)}
                            title={folderBusy ? busyAction || 'Working…' : collapsedFolders.includes(folder.path) ? 'Expand' : 'Collapse'}
                          >
                            <span className={folderBusy ? 'folderToggleIcon loading' : 'folderToggleIcon'}>
                              {folderBusy ? (
                                <RefreshCw size={14} className="folderStateIcon spinning" aria-hidden="true" />
                              ) : (
                                <>
                                  {collapsedFolders.includes(folder.path) ? <Folder size={14} className="folderStateIcon" /> : <FolderOpen size={14} className="folderStateIcon" />}
                                  {collapsedFolders.includes(folder.path) ? <ChevronRight size={14} className="folderCaretIcon" /> : <ChevronDown size={14} className="folderCaretIcon" />}
                                </>
                              )}
                            </span>
                          </button>
                          <button
                            className="folderGroupToggle"
                            onClick={() => void openTargetPath(folder.path, { asLibrary: true })}
                            onKeyDown={(event) => {
                              if (event.key !== 'ContextMenu' && !(event.shiftKey && event.key === 'F10')) return;
                              event.preventDefault();
                              const bounds = event.currentTarget.getBoundingClientRect();
                              showFolderContextMenu(folder.path, bounds.left, bounds.bottom);
                            }}
                            title="Use this folder as the active library"
                            aria-haspopup="menu"
                            aria-expanded={folderContextMenu?.path === folder.path}
                          >
                            <span className="folderGroupName">{folder.name}</span>
                          </button>
                          <button
                            type="button"
                            className={`indexBadge ${indexBadgeClass}`}
                            title={indexBadgeTitle}
                            aria-label={`Index status: ${folderIndexing ? 'indexing' : folderIndexChecking && !folderIndex ? 'checking' : folderIndexReport?.skipped ? `indexed with ${folderIndexReport.skipped} skipped` : folderIndex?.fresh ? 'indexed' : folderIndex?.exists ? 'needs updating' : 'no index'}`}
                            disabled={Boolean(folderIndexing) || !folderIndexReport}
                            onClick={() => {
                              if (!folderIndexReport) return;
                              setIndexPrompt(null);
                              setIndexReport(folderIndexReport);
                            }}
                          >
                            {folderIndexing
                              ? <RefreshCw size={11} className="spinning" aria-hidden="true" />
                              : folderIndexChecking && !folderIndex
                                ? <RefreshCw size={11} className="spinning" aria-hidden="true" />
                              : folderIndexReport?.skipped
                                ? <AlertTriangle size={11} aria-hidden="true" />
                                : <Database size={11} aria-hidden="true" />}
                          </button>
                        </div>
                        {collapsedFolders.includes(folder.path) ? null : visibleEntries.length === 0 ? (
                          <p className="folderEmpty">
                            {explorerFileFilter === 'all'
                              ? 'No .vera or .pdf files'
                              : `No .${explorerFileFilter} files`}
                          </p>
                        ) : (
                          visibleEntries.map((entry) => (
                            <div key={entry.path} className="fileRowWrap">
                              {entry.type === 'vera' ? (
                                <input
                                  type="checkbox"
                                  className="fileRowCheck"
                                  checked={selectedFiles.includes(entry.path)}
                                  onChange={() => toggleSelectedFile(entry.path)}
                                  title="Include in search scope"
                                />
                              ) : (
                                <span className="fileRowCheckSpacer" />
                              )}
                              <button
                                className={path === entry.path || pdfPath === entry.path ? 'fileRow active' : 'fileRow'}
                                onClick={() => openEntry(entry)}
                                onContextMenu={(event) => {
                                  event.preventDefault();
                                  showEntryContextMenu(entry, folder.path, event.clientX, event.clientY);
                                }}
                                title={entry.relativePath}
                              >
                                {entry.type === 'vera' ? <VeraIcon size={14} className="fileRowIcon vera" /> : <FileText size={14} className="fileRowIcon pdf" />}
                                <span className="fileRowName">{entry.relativePath}</span>
                              </button>
                            </div>
                          ))
                        )}
                      </section>
                      );
                      })}
                    </div>
                  </>
                )
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

              {sideView === 'search' ? (
                <div className="searchView">
                  <div className="searchBox">
                    <textarea
                      className="searchInput"
                      value={searchQuery}
                      rows={3}
                      onChange={(event) => setSearchQuery(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
                          event.preventDefault();
                          void searchTarget();
                        }
                      }}
                      placeholder="Search the active scope…"
                    />
                    <div className="searchScope">
                      <span>{selectedFiles.length > 0
                        ? `${selectedFiles.length} selected document${selectedFiles.length === 1 ? '' : 's'}`
                        : activeLibraryIsEmpty ? 'Empty library'
                        : activeLibraryPath ? 'Entire library' : path ? 'Current document' : 'No search scope'}</span>
                      {selectedFiles.length > 0 ? (
                        <button type="button" onClick={() => setSelectedFiles([])} title="Clear selection">Clear</button>
                      ) : null}
                    </div>
                    <div className="searchControls">
                      <label className="miniField">
                        <span>Mode</span>
                        <select value={mode} onChange={(event) => setMode(event.target.value)}>
                          <option value="hybrid">Hybrid</option>
                          <option value="semantic">Semantic</option>
                          <option value="keyword">Keyword</option>
                        </select>
                      </label>
                      <label className="miniField">
                        <span>Top K</span>
                        <input className="numberInput" type="number" min={1} max={50} value={topK} onChange={(event) => setTopK(Number(event.target.value))} />
                      </label>
                      <label className="miniField">
                        <span>Context</span>
                        <input className="numberInput" type="number" min={0} max={5} value={contextChunks} onChange={(event) => setContextChunks(Number(event.target.value))} />
                      </label>
                      <label className="miniCheck">
                        <input type="checkbox" checked={includeFigures} onChange={(event) => setIncludeFigures(event.target.checked)} />
                        <span>Figures</span>
                      </label>
                    </div>
                    <button className="sidePrimary" onClick={searchTarget} disabled={!hasSearchableScope || !searchQuery.trim() || busy}><Search size={15} />Search</button>
                  </div>
                  <div className="searchResults">
                    {results.length === 0 ? (
                      <p className="sideMuted">{searchScopePath ? 'No results yet.' : 'Open a document or library first.'}</p>
                    ) : (
                      results.map((result) => (
                        <button
                          className={selected?.chunk_id === result.chunk_id ? 'resultRow active' : 'resultRow'}
                          key={`${result.file || result.document_id}-${result.chunk_id}`}
                          onClick={() => { selectSearchResult(result); setViewerMode('document'); }}
                        >
                          <span className="resultRowMeta">{result.score.toFixed(3)} · p. {formatPages(result.page_start, result.page_end)}{result.file ? ` · ${result.file}` : ''}</span>
                          <strong>{result.heading_path || result.source_filename || result.chunk_id}</strong>
                          <span className="resultRowText">{result.text}</span>
                        </button>
                      ))
                    )}
                  </div>
                </div>
              ) : null}

              {sideView === 'convert' ? (
                <div className="convertView">
                  <div className="convertModeToggle">
                    <button className={convertMode === 'single' ? 'active' : ''} onClick={() => setConvertMode('single')}>Single PDF</button>
                    <button className={convertMode === 'batch' ? 'active' : ''} onClick={() => setConvertMode('batch')}>PDF Directory</button>
                  </div>
                  {convertMode === 'single' ? (
                    <>
                      <label className="field">
                        <span>PDF</span>
                        <div className="pathInput">
                          <FileInput size={16} />
                          <input
                            value={pdfPath}
                            onChange={(event) => {
                              const value = event.target.value;
                              setPdfPath(value);
                              if (!outputPath.trim()) setOutputPath(defaultVeraPath(value));
                            }}
                            placeholder="C:\\docs\\manual.pdf"
                          />
                        </div>
                      </label>
                      <button className="secondaryAction" onClick={choosePdf} disabled={busy || conversionInProgress}><FolderOpen size={16} />Choose PDF</button>
                      <label className="field">
                        <span>Output</span>
                        <div className="pathInput">
                          <VeraIcon size={16} />
                          <input value={outputPath} onChange={(event) => setOutputPath(event.target.value)} placeholder="C:\\docs\\manual.vera" />
                        </div>
                      </label>
                      <button className="secondaryAction" onClick={chooseOutput} disabled={busy || conversionInProgress}><FolderOpen size={16} />Save As</button>
                    </>
                  ) : (
                    <>
                      <label className="field">
                        <span>PDF directory</span>
                        <div className="pathInput">
                          <Folder size={16} />
                          <input value={batchDirectory} onChange={(event) => setBatchDirectory(event.target.value)} placeholder="C:\\proposals" />
                        </div>
                      </label>
                      <button className="secondaryAction" onClick={chooseBatchDirectory} disabled={busy || conversionInProgress}><FolderOpen size={16} />Choose Directory</button>
                      <label className="miniCheck">
                        <input type="checkbox" checked={batchRecursive} onChange={(event) => setBatchRecursive(event.target.checked)} />
                        <span>Include PDFs in nested folders</span>
                      </label>
                      <label className="miniCheck">
                        <input type="checkbox" checked={batchOverwrite} onChange={(event) => setBatchOverwrite(event.target.checked)} />
                        <span>Overwrite existing .vera files</span>
                      </label>
                      <p className="sideMuted">Each archive is created beside its PDF with the same base filename. Existing archives are skipped unless overwrite is enabled.</p>
                    </>
                  )}
                  <p className="sideMuted">Conversions use the PyMuPDF parser and local hashing embeddings.</p>
                  <div className="convertGrid">
                    <label className="miniField">
                      <span>Chunk Size</span>
                      <input className="numberInput" type="number" min={100} max={3000} step={50} value={chunkSize} onChange={(event) => setChunkSize(Number(event.target.value))} />
                    </label>
                    <label className="miniField">
                      <span>Overlap</span>
                      <input className="numberInput" type="number" min={0} max={1000} step={25} value={overlap} onChange={(event) => setOverlap(Number(event.target.value))} />
                    </label>
                  </div>
                  <label className="miniCheck">
                    <input type="checkbox" checked={storeOriginal} onChange={(event) => setStoreOriginal(event.target.checked)} />
                    <span>Store original PDF</span>
                  </label>
                  <div className="convertActions">
                    <button
                      className="sidePrimary"
                      onClick={convertMode === 'single' ? convertPdf : batchConvertPdfs}
                      disabled={convertMode === 'single'
                        ? !pdfPath.trim() || busy || conversionInProgress
                        : !batchDirectory.trim() || busy || conversionInProgress}
                    >
                      <RefreshCw size={16} className={conversionInProgress ? 'spinning' : undefined} />
                      {conversionInProgress
                        ? 'Converting…'
                        : convertMode === 'single'
                          ? 'Convert'
                          : 'Convert Directory'}
                    </button>
                    {conversionInProgress && convertMode === 'batch' ? (
                      <button
                        type="button"
                        className="secondaryAction convertStop"
                        onClick={skipCurrentConversion}
                        disabled={conversionStatus === 'Stopping…'}
                        title="Skip current file and continue"
                        aria-label="Skip current file"
                      >
                        <SkipForward size={14} />
                        Skip
                      </button>
                    ) : null}
                    {conversionInProgress ? (
                      <button
                        type="button"
                        className="secondaryAction convertStop"
                        onClick={stopConversion}
                        disabled={conversionStatus === 'Stopping…'}
                        title="Stop conversion"
                        aria-label="Stop conversion"
                      >
                        <Square size={12} fill="currentColor" />
                        Stop
                      </button>
                    ) : null}
                  </div>
                  {conversionInProgress && conversionStatus ? (
                    <p className="conversionStatusText">{conversionStatus}</p>
                  ) : null}
                  {conversionInProgress && conversionCurrentFile ? (
                    <p className="conversionCurrentFile" title={conversionCurrentFile}>
                      {conversionCurrentFile}
                    </p>
                  ) : null}
                  {conversionError ? <p className="sideMuted" role="alert">{conversionError}</p> : null}
                  {convertMode === 'single' && convertResult ? <p className="sideMuted">Created {convertResult.output}</p> : null}
                  {convertMode === 'batch' && batchConvertResult ? (
                    <div className="batchConvertReport">
                      <strong>{batchConvertResult.converted} converted</strong>
                      <span>
                        {batchConvertResult.discovered} PDFs found · {batchConvertResult.skipped} skipped
                        {batchConvertResult.user_skipped ? ` · ${batchConvertResult.user_skipped} user-skipped` : ''}
                        {' · '}{batchConvertResult.malformed} malformed · {batchConvertResult.failed} failed
                      </span>
                      {batchConvertResult.malformed_existing.map((entry) => (
                        <span className="batchConvertError" key={entry.output} title={entry.issues.join('; ')}>{entry.output}: {entry.issues.join('; ')}</span>
                      ))}
                      {(batchConvertResult.skipped_by_user || []).map((filePath) => (
                        <span className="batchConvertSkipped" key={filePath} title="Skipped by user">{filePath}: skipped</span>
                      ))}
                      {batchConvertResult.errors.map((entry) => (
                        <span className="batchConvertError" key={entry.input} title={entry.error}>{entry.input}: {entry.error}</span>
                      ))}
                    </div>
                  ) : null}
                </div>
              ) : null}

              {sideView === 'info' ? (
                <div className="infoView">
                  {path ? (
                    <>
                      <div className="infoActions">
                        <button className="secondaryAction" onClick={inspectTarget} disabled={!path.trim() || activeLibraryIsEmpty || busy}><ShieldCheck size={15} />{isCorpus ? 'Deep inspect' : 'Inspect'}</button>
                        <button className="secondaryAction" onClick={validateTarget} disabled={!path.trim() || isCorpus || busy}><CheckCircle2 size={15} />Validate</button>
                        <button className="secondaryAction" onClick={exportSource} disabled={!path.trim() || isCorpus || busy}><Download size={15} />Export</button>
                      </div>
                      <dl className="infoList">
                        <div><dt>Format</dt><dd>{inspect ? `${inspect.format_name || 'VERA'} ${inspect.format_version || ''}` : '-'}</dd></div>
                        <div><dt>Source</dt><dd>{inspect?.source || inspect?.directory || '-'}</dd></div>
                        <div><dt>Pages</dt><dd>{inspect?.pages ?? '-'}</dd></div>
                        <div><dt>Chunks</dt><dd>{inspect?.chunks ?? '-'}</dd></div>
                        <div><dt>Model</dt><dd>{inspect?.default_embedding_model || inspect?.embedding_models?.join(', ') || '-'}</dd></div>
                        {isCorpus ? <div><dt>Summary</dt><dd>{inspect?.summary_source === 'index' ? 'Persistent index' : inspect?.summary_source === 'archives' ? 'Deep archive scan' : 'File discovery only'}</dd></div> : null}
                        <div><dt>Validation</dt><dd>{validation ? (validation.ok ? 'PASS' : 'FAIL') : '-'}</dd></div>
                        <div><dt>Issues</dt><dd>{validation?.issues?.length ? validation.issues.join('; ') : '0'}</dd></div>
                        <div><dt>Export</dt><dd>{exportResult?.output || '-'}</dd></div>
                      </dl>
                      {sourceDocument ? (
                        <section className="infoSection">
                          <h3>Source Document</h3>
                          <dl className="infoList">
                            <div><dt>File</dt><dd>{sourceDocument.filename}</dd></div>
                            <div><dt>Type</dt><dd>{sourceDocument.mime_type}</dd></div>
                            <div><dt>Size</dt><dd>{Math.round(sourceDocument.size / 1024).toLocaleString()} KB</dd></div>
                          </dl>
                        </section>
                      ) : null}
                      <section className="infoSection">
                        <h3>Page Text</h3>
                        <div className="pageControls">
                          <input className="numberInput" type="number" min={1} max={inspect?.pages || undefined} value={pageNumber} onChange={(event) => setPageNumber(Number(event.target.value))} />
                          <button className="secondaryAction" onClick={loadPage} disabled={!path.trim() || isCorpus || busy}>Load Page</button>
                        </div>
                        {pageResult ? (
                          <article className="pageText">
                            <span>p. {pageResult.page_number} · {pageResult.width ?? '-'} x {pageResult.height ?? '-'}</span>
                            <p>{pageResult.text || 'No text was extracted for this page.'}</p>
                          </article>
                        ) : (
                          <p className="sideMuted">Load a page to inspect extracted text.</p>
                        )}
                      </section>
                    </>
                  ) : (
                    <div className="sideEmpty">
                      <Info size={28} />
                      <p>Open a document to see its details.</p>
                    </div>
                  )}
                </div>
              ) : null}
            </div>
          </aside>
        ) : null}

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

        <main className="centerPane">
          <header className="centerHeader">
            <button className="centerNewChat" onClick={() => void newSession()} title="Start a new chat"><Plus size={14} />New chat</button>
            <span className="centerStatus">{busyAction === 'Asking' ? 'Ready' : status}</span>
            {viewerCollapsed ? (
              <button
                type="button"
                className="ghostIcon"
                onClick={() => setViewerCollapsed(false)}
                title="Open document viewer"
                aria-label="Open document viewer"
              >
                <Maximize2 size={15} />
              </button>
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
                  setStatus('Ready');
                }}
              >
                <X size={14} />
              </button>
            </div>
          ) : null}
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
                        {streamEvents.length > 0 ? (
                          <ActivityTrace
                            live
                            searches={streamEvents.map((ev) => ({
                              query: ev.query || '',
                              mode: ev.mode,
                              hits: ev.hits,
                              pending: ev.event !== 'search_done',
                            }))}
                          />
                        ) : null}
                        {streamingAnswer ? (
                          <div className="markdownBody"><Markdown remarkPlugins={[remarkGfm]}>{streamingAnswer}</Markdown></div>
                        ) : null}
                        {showTrace && traceEvents.length > 0 ? <TraceView events={traceEvents} /> : null}
                        <div className="responseStatus"><span className="statusDot" />{responseStatus}</div>
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
                      : activeLibraryIsEmpty ? 'Empty library'
                      : activeLibraryPath ? 'Entire library' : path ? 'Current document' : 'No search scope'}
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
        </main>

        {!viewerCollapsed ? (
          <>
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

        <aside className="viewerPane">
          <div className="viewerHeader">
            <div className="viewerTitleGroup">
              <h2>{selected && viewerMode === 'selection' ? 'Chunk Details' : 'Document Viewer'}</h2>
              <span title={selected ? citation : sourceDocument?.filename || ''}>{selected && viewerMode === 'selection' ? citation : sourceDocument?.filename || 'No document loaded'}</span>
            </div>
            <div className="viewerHeaderActions">
              {selected ? (
                <div className="viewerModeToggle">
                  <button className={viewerMode === 'document' ? 'active' : ''} onClick={() => { setViewerMode('document'); if (!sourceDocument && selectedSourcePath) void loadSourceDocument(selectedSourcePath, false); }} title="Show full document">Document</button>
                  <button className={viewerMode === 'selection' ? 'active' : ''} onClick={() => setViewerMode('selection')} title="Show chunk debug data">Details</button>
                </div>
              ) : null}
              <button className="ghostIcon" onClick={() => setSourcePaneWidth(sourceExpanded ? 34 : 64)} title={sourceExpanded ? 'Restore viewer' : 'Expand viewer'} aria-label={sourceExpanded ? 'Restore viewer' : 'Expand viewer'}>
                {sourceExpanded ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
              </button>
              <button
                type="button"
                className="ghostIcon"
                onClick={() => setViewerCollapsed(true)}
                title="Close document viewer"
                aria-label="Close document viewer"
              >
                <X size={15} />
              </button>
            </div>
          </div>
          {selected && viewerMode === 'selection' ? (
            <article className="sourceDetails sourceViewerOnly">
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
          ) : sourceDocument && isPdfSource(sourceDocument) ? (
            <div className="sourceViewer">
              <PdfSourceViewer
                source={sourceDocument}
                highlightRegions={viewerHighlights.regions}
                highlightFigures={viewerHighlights.figures}
                targetPage={viewerHighlights.targetPage}
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
          )}
        </aside>
          </>
        ) : null}
      </div>
      <footer className="statusbar">
        <span className="statusPath">{path || 'No file open'}</span>
        <span>Pages: {inspect?.pages ?? '-'}</span>
        <span>Chunks: {inspect?.chunks ?? '-'}</span>
        <span>Files: {inspect?.file_count ?? '-'}</span>
        <span>Model: {inspect?.default_embedding_model || inspect?.embedding_models?.join(', ') || '-'}</span>
      </footer>
      {folderContextMenu ? (
        <div className="folderContextMenuBackdrop" onClick={() => setFolderContextMenu(null)}>
          <div
            className="folderContextMenu"
            role="menu"
            style={{ left: folderContextMenu.x, top: folderContextMenu.y }}
            onClick={(event) => event.stopPropagation()}
          >
            <button
              ref={folderContextMenuFirstActionRef}
              role="menuitem"
              onClick={() => {
                void openTargetPath(folderContextMenu.path, { asLibrary: true });
                setFolderContextMenu(null);
              }}
            >
              Use as active library
            </button>
            <button
              role="menuitem"
              disabled={Boolean(indexingFolders[folderContextMenu.path])}
              onClick={() => {
                void manageLibraryIndex(folderContextMenu.path);
                setFolderContextMenu(null);
              }}
            >
              {indexingFolders[folderContextMenu.path]
                ? 'Indexing…'
                : indexStatuses[folderContextMenu.path]?.exists ? 'Update index' : 'Build index'}
            </button>
            <button
              role="menuitem"
              onClick={() => {
                void refreshFolder(folderContextMenu.path);
                setFolderContextMenu(null);
              }}
            >
              Rescan folder
            </button>
            <div className="folderContextMenuSeparator" role="separator" />
            <button
              className="danger"
              role="menuitem"
              onClick={() => {
                removeFolder(folderContextMenu.path);
                setFolderContextMenu(null);
              }}
            >
              Close folder
            </button>
          </div>
        </div>
      ) : null}
      {entryContextMenu ? (
        <div className="folderContextMenuBackdrop" onClick={() => setEntryContextMenu(null)}>
          <div
            className="folderContextMenu"
            role="menu"
            style={{ left: entryContextMenu.x, top: entryContextMenu.y }}
            onClick={(event) => event.stopPropagation()}
          >
            {entryContextMenu.entry.type === 'vera' ? (
              <button
                ref={entryContextMenuActionRef}
                role="menuitem"
                onClick={() => {
                  void previewSourceDocument(entryContextMenu.entry);
                  setEntryContextMenu(null);
                }}
              >
                Preview embedded source
              </button>
            ) : null}
            {entryContextMenu.entry.type === 'vera' ? <div className="folderContextMenuSeparator" role="separator" /> : null}
            <button
              ref={entryContextMenu.entry.type === 'vera' ? undefined : entryContextMenuActionRef}
              className="danger"
              role="menuitem"
              onClick={() => {
                void trashEntry(entryContextMenu.entry, entryContextMenu.folderPath);
                setEntryContextMenu(null);
              }}
            >
              Move to Recycle Bin
            </button>
          </div>
        </div>
      ) : null}
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
