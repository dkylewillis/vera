import React, { type CSSProperties, type ReactNode, useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import * as pdfjsLib from 'pdfjs-dist';
import pdfWorkerUrl from 'pdfjs-dist/build/pdf.worker.mjs?url';
import {
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Download,
  FileInput,
  FileSearch,
  FileText,
  Files,
  Folder,
  FolderOpen,
  Highlighter,
  Info,
  KeyRound,
  ListChecks,
  Maximize2,
  MessageSquareText,
  Minimize2,
  PanelLeftClose,
  Pencil,
  Plus,
  RefreshCw,
  RotateCw,
  Search,
  Send,
  Settings,
  ShieldCheck,
  Sparkles,
  Terminal,
  Trash2,
  X,
} from 'lucide-react';
import type { AppSettings, ChatAnswerResult, ChatCitationResult, ConvertResult, ExportResult, FolderEntry, InspectResult, Mode, PageResult, ProviderProfile, RegionResult, SearchResult, Session, SessionTurn, StreamEvent, SourceDocumentResult, ValidateResult, WorkspaceFolderResult } from './types';
import './styles.css';

type SideView = 'explorer' | 'chats' | 'search' | 'convert' | 'info';

const EMPTY_REGIONS: RegionResult[] = [];

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

type ProviderPreset = { key: string; label: string; value: Omit<ProviderProfile, 'id'> };

const PROVIDER_PRESETS: ProviderPreset[] = [
  {
    key: 'ollama',
    label: 'Ollama',
    value: { label: 'Ollama', provider: 'ollama', models: [], base_url: 'http://localhost:11434/v1', api_key_env: '', auth_type: 'none', temperature: 0.2 },
  },
  {
    key: 'lmstudio',
    label: 'LM Studio',
    value: { label: 'LM Studio', provider: 'lmstudio', models: [], base_url: 'http://localhost:1234/v1', api_key_env: '', auth_type: 'none', temperature: 0.2 },
  },
  {
    key: 'openai',
    label: 'OpenAI',
    value: { label: 'OpenAI', provider: 'openai_compatible', models: [], base_url: 'https://api.openai.com/v1', api_key_env: 'OPENAI_API_KEY', auth_type: 'api_key', temperature: 0.2 },
  },
  {
    key: 'openrouter',
    label: 'OpenRouter',
    value: { label: 'OpenRouter', provider: 'openai_compatible', models: [], base_url: 'https://openrouter.ai/api/v1', api_key_env: 'OPENROUTER_API_KEY', auth_type: 'api_key', temperature: 0.2 },
  },
];

function newProviderId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `prov_${crypto.randomUUID()}`;
  }
  return `prov_${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`;
}

function emptyProvider(): ProviderProfile {
  return {
    id: newProviderId(),
    label: 'New Provider',
    provider: 'openai_compatible',
    models: [],
    base_url: 'https://api.openai.com/v1',
    api_key_env: 'OPENAI_API_KEY',
    auth_type: 'api_key',
    temperature: 0.2,
  };
}

function providerTypeLabel(provider: string): string {
  switch (provider) {
    case 'ollama':
      return 'Ollama';
    case 'lmstudio':
    case 'lm_studio':
      return 'LM Studio';
    case 'openai':
      return 'OpenAI';
    default:
      return 'OpenAI Compatible';
  }
}

function providerDisplayName(profile: ProviderProfile): string {
  return profile.label.trim() || providerTypeLabel(profile.provider);
}

pdfjsLib.GlobalWorkerOptions.workerSrc = pdfWorkerUrl;

function formatPages(start: number | null, end: number | null): string {
  if (start === null && end === null) return '-';
  if (start === end || end === null) return String(start);
  if (start === null) return String(end);
  return `${start}-${end}`;
}

function formatBox(box: number[] | undefined): string {
  if (!box?.length) return '-';
  return box.map((value) => Math.round(value)).join(', ');
}

function defaultVeraPath(pdf: string): string {
  const trimmed = pdf.trim();
  if (!trimmed) return '';
  return trimmed.toLowerCase().endsWith('.pdf') ? `${trimmed.slice(0, -4)}.vera` : `${trimmed}.vera`;
}

function isPdfSource(source: SourceDocumentResult | null): boolean {
  if (!source) return false;
  return source.mime_type === 'application/pdf' || source.filename.toLowerCase().endsWith('.pdf');
}

function regionStyle(region: RegionResult): CSSProperties {
  const [x0, y0, x1, y1] = region.bbox || [];
  if (!region.page_width || !region.page_height || x0 === undefined || y0 === undefined || x1 === undefined || y1 === undefined) {
    return {};
  }
  return {
    left: `${(x0 / region.page_width) * 100}%`,
    top: `${(y0 / region.page_height) * 100}%`,
    width: `${((x1 - x0) / region.page_width) * 100}%`,
    height: `${((y1 - y0) / region.page_height) * 100}%`,
  };
}

const PDF_ZOOM_MIN = 0.75;
const PDF_ZOOM_MAX = 2.5;
const PDF_ZOOM_DEFAULT = 1.25;
const PDF_ZOOM_STEP = 0.25;

function clampPdfZoom(value: number): number {
  return Math.min(PDF_ZOOM_MAX, Math.max(PDF_ZOOM_MIN, Math.round(value * 100) / 100));
}

function PdfSourceViewerImpl({
  source,
  highlightRegions = EMPTY_REGIONS,
  compact = false,
  targetPage,
}: {
  source: SourceDocumentResult;
  highlightRegions?: RegionResult[];
  compact?: boolean;
  targetPage?: number | null;
}) {
  const pagesRef = useRef<HTMLDivElement | null>(null);
  const pdfRef = useRef<pdfjsLib.PDFDocumentProxy | null>(null);
  const renderedSourceRef = useRef('');
  const [scale, setScale] = useState(PDF_ZOOM_DEFAULT);
  const [error, setError] = useState<string | null>(null);
  const [pageCount, setPageCount] = useState(0);
  const [rendering, setRendering] = useState(false);
  const [showHighlights, setShowHighlights] = useState(() => {
    try { return localStorage.getItem('vera.showHighlights') !== '0'; } catch { return true; }
  });
  const highlightKey = useMemo(() => JSON.stringify(highlightRegions), [highlightRegions]);

  // Scroll-only effect: targetPage changes just scroll, never re-render.
  useEffect(() => {
    if (!targetPage || !pagesRef.current) return;
    const target = pagesRef.current.querySelector<HTMLElement>(`[data-page-number="${targetPage}"]`);
    if (target) pagesRef.current.scrollTo({ top: target.offsetTop, behavior: 'smooth' });
  }, [targetPage]);

  // Ctrl/Cmd + mouse wheel (and trackpad pinch, which Chromium reports as a wheel
  // event with ctrlKey set) zooms the viewer, like a standard PDF/browser viewer.
  // Wheel deltas are coalesced per animation frame so a fast scroll gesture doesn't
  // trigger a full page re-render on every tick.
  useEffect(() => {
    const container = pagesRef.current;
    if (!container) return;
    let rafId: number | null = null;
    let pendingFactor = 1;

    const commit = () => {
      rafId = null;
      const factor = pendingFactor;
      pendingFactor = 1;
      setScale((value) => clampPdfZoom(value * factor));
    };

    const onWheel = (event: WheelEvent) => {
      if (!event.ctrlKey && !event.metaKey) return;
      event.preventDefault();
      pendingFactor *= 1 - event.deltaY * 0.0015;
      if (rafId == null) rafId = requestAnimationFrame(commit);
    };

    container.addEventListener('wheel', onWheel, { passive: false });
    return () => {
      container.removeEventListener('wheel', onWheel);
      if (rafId != null) cancelAnimationFrame(rafId);
    };
  }, []);

  // Ctrl/Cmd +, -, 0 zoom the viewer, matching standard PDF-viewer hotkeys. Scoped to
  // the viewer's own key handler so it only fires while the viewer has focus.
  const onViewerKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (!event.ctrlKey && !event.metaKey) return;
    if (event.key === '=' || event.key === '+') {
      event.preventDefault();
      setScale((value) => clampPdfZoom(value + PDF_ZOOM_STEP));
    } else if (event.key === '-') {
      event.preventDefault();
      setScale((value) => clampPdfZoom(value - PDF_ZOOM_STEP));
    } else if (event.key === '0') {
      event.preventDefault();
      setScale(PDF_ZOOM_DEFAULT);
    }
  };


  // Main render effect: load PDF + set up virtualized rendering.
  // targetPage deliberately excluded from deps — handled by scroll effect above.
  useEffect(() => {
    let canceled = false;
    let observer: IntersectionObserver | null = null;

    async function load() {
      setError(null);
      setRendering(true);
      try {
        // Re-use cached PDFDocument across highlight/scale changes for the same file.
        if (!pdfRef.current || renderedSourceRef.current !== source.data_url) {
          const bytes = await fetch(source.data_url).then((r) => r.arrayBuffer());
          if (canceled) return;
          pdfRef.current = await pdfjsLib.getDocument({
            data: new Uint8Array(bytes),
            useWorkerFetch: false,
          }).promise;
          renderedSourceRef.current = source.data_url;
        }
        const pdf = pdfRef.current;
        if (!pdf || canceled) return;

        setPageCount(pdf.numPages);
        const container = pagesRef.current;
        if (!container) return;
        container.scrollTop = 0;
        container.replaceChildren();

        // Get first-page dimensions to pre-size all placeholder shells.
        const firstPage = await pdf.getPage(1);
        if (canceled) return;
        const defaultViewport = firstPage.getViewport({ scale });
        const defaultW = Math.floor(defaultViewport.width);
        const defaultH = Math.floor(defaultViewport.height);

        // Build placeholder shells for every page — no rendering yet.
        const shells: HTMLElement[] = [];
        for (let i = 1; i <= pdf.numPages; i++) {
          const shell = document.createElement('article');
          shell.className = 'pdfPage pdfPage--pending';
          shell.dataset.pageNumber = String(i);
          const label = document.createElement('span');
          label.textContent = `Page ${i}`;
          const surface = document.createElement('div');
          surface.className = 'pdfPageSurface';
          surface.style.width = `${defaultW}px`;
          surface.style.height = `${defaultH}px`;
          shell.append(label, surface);
          container.append(shell);
          shells.push(shell);
        }

        // Renders a single page into its already-appended shell.
        const renderPage = async (pageNum: number) => {
          const shell = shells[pageNum - 1];
          if (!shell || shell.dataset.rendered) return;
          shell.dataset.rendered = '1';
          shell.classList.remove('pdfPage--pending');

          const page = await pdf.getPage(pageNum);
          if (canceled) return;
          const viewport = page.getViewport({ scale });
          const w = Math.floor(viewport.width);
          const h = Math.floor(viewport.height);

          const surface = shell.querySelector<HTMLElement>('.pdfPageSurface')!;
          surface.style.width = `${w}px`;
          surface.style.height = `${h}px`;

          const canvas = document.createElement('canvas');
          canvas.width = w;
          canvas.height = h;
          const ctx = canvas.getContext('2d')!;

          const highlightLayer = document.createElement('div');
          highlightLayer.className = 'pdfHighlightLayer';
          for (const region of highlightRegions.filter((r) => r.page_number === pageNum && r.bbox?.length === 4)) {
            const box = document.createElement('div');
            box.className = 'pdfHighlightBox';
            Object.assign(box.style, regionStyle(region));
            highlightLayer.append(box);
          }

          const textLayerContainer = document.createElement('div');
          textLayerContainer.className = 'textLayer';

          surface.replaceChildren(canvas, highlightLayer, textLayerContainer);
          await page.render({ canvas, canvasContext: ctx, viewport }).promise;
          if (canceled) return;
          await new pdfjsLib.TextLayer({
            textContentSource: page.streamTextContent(),
            container: textLayerContainer,
            viewport,
          }).render();
        };

        // Render the jump-target page (or page 1) first for instant feedback.
        const priority = targetPage ?? 1;
        await renderPage(priority);
        if (canceled) return;

        // Position scroll before painting the rest.
        const priorityShell = container.querySelector<HTMLElement>(`[data-page-number="${priority}"]`);
        if (priorityShell) container.scrollTo({ top: priorityShell.offsetTop });

        // Lazily render remaining pages as they scroll into view (200 px margin).
        observer = new IntersectionObserver(
          (entries) => {
            for (const entry of entries) {
              if (!entry.isIntersecting) continue;
              const el = entry.target as HTMLElement;
              const num = Number(el.dataset.pageNumber);
              if (num && !el.dataset.rendered) void renderPage(num);
            }
          },
          { root: container, rootMargin: '300px 0px' },
        );
        for (const shell of shells) observer.observe(shell);

      } catch (err) {
        if (!canceled) setError(err instanceof Error ? err.message : 'Unable to render PDF');
      } finally {
        if (!canceled) setRendering(false);
      }
    }

    void load();
    return () => {
      canceled = true;
      observer?.disconnect();
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [highlightKey, scale, source.data_url]); // targetPage intentionally excluded

  return (
    <div className={`${compact ? 'pdfViewer compact' : 'pdfViewer'}${showHighlights ? '' : ' pdfViewer--hideHighlights'}`}>
      <div className="viewerToolbar">
        <span>{rendering ? 'Rendering' : `${pageCount || '-'} pages`}</span>
        <button
          type="button"
          className={showHighlights ? 'secondaryAction activeNow' : 'secondaryAction'}
          onClick={() => setShowHighlights((value) => {
            const next = !value;
            try { localStorage.setItem('vera.showHighlights', next ? '1' : '0'); } catch { /* ignore persistence errors */ }
            return next;
          })}
          title={showHighlights ? 'Hide highlight regions' : 'Show highlight regions'}
        >
          <Highlighter size={14} />Highlights
        </button>
        <button className="secondaryAction" onClick={() => setScale((value) => clampPdfZoom(value - PDF_ZOOM_STEP))}>Zoom Out</button>
        <span className="zoomLevel">{Math.round(scale * 100)}%</span>
        <button className="secondaryAction" onClick={() => setScale((value) => clampPdfZoom(value + PDF_ZOOM_STEP))}>Zoom In</button>
      </div>
      {error ? <div className="errorBanner">{error}</div> : null}
      <div className="pdfCanvasWrap" ref={pagesRef} tabIndex={0} onKeyDown={onViewerKeyDown} />
    </div>
  );
}

// Memoized so this doesn't re-render (and re-run its render body) when unrelated
// App state changes, e.g. every keystroke in the chat composer.
const PdfSourceViewer = React.memo(PdfSourceViewerImpl);

function renderAnswerWithCitations(answerText: string, citations: ChatCitationResult[], selectCitation: (citation: ChatCitationResult) => void) {
  const citationById = new Map(citations.map((citation) => [citation.id, citation]));

  // Replace any string child containing `[C#]` markers with clickable citation buttons,
  // leaving the surrounding markdown-rendered elements intact.
  const injectCitations = (children: ReactNode): ReactNode =>
    React.Children.map(children, (child, index) => {
      if (typeof child !== 'string') return child;
      if (!child.includes('[C')) return child;
      return child.split(/(\[C\d+\])/g).map((part, partIndex) => {
        const id = part.match(/^\[(C\d+)\]$/)?.[1];
        const citation = id ? citationById.get(id) : null;
        if (!citation) return <React.Fragment key={`t-${index}-${partIndex}`}>{part}</React.Fragment>;
        return (
          <button className="inlineCitation" key={`c-${index}-${partIndex}`} onClick={() => selectCitation(citation)}>
            {part}
          </button>
        );
      });
    });

  const withCitations =
    (Tag: keyof React.JSX.IntrinsicElements) =>
    ({ children, ...props }: { children?: ReactNode }) =>
      React.createElement(Tag, props, injectCitations(children));

  return (
    <div className="markdownBody">
      <Markdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: withCitations('p'),
          li: withCitations('li'),
          td: withCitations('td'),
          th: withCitations('th'),
          h1: withCitations('h1'),
          h2: withCitations('h2'),
          h3: withCitations('h3'),
          h4: withCitations('h4'),
          h5: withCitations('h5'),
          h6: withCitations('h6'),
          strong: withCitations('strong'),
          em: withCitations('em'),
          blockquote: withCitations('blockquote'),
          a: ({ children, ...props }) => (
            <a {...props} target="_blank" rel="noreferrer">{injectCitations(children)}</a>
          ),
        }}
      >
        {answerText}
      </Markdown>
    </div>
  );
}

type ActivitySearchItem = { query: string; mode?: string; hits?: number; pending?: boolean };

type ActivityStep =
  | { kind: 'search'; item: ActivitySearchItem }
  | { kind: 'source'; citation: ChatCitationResult };

function ActivityStepRow({
  step,
  onSelectCitation,
  selected,
}: {
  step: ActivityStep;
  onSelectCitation?: (citation: ChatCitationResult) => void;
  selected?: boolean;
}) {
  if (step.kind === 'search') {
    const { item } = step;
    return (
      <li className={item.pending ? 'activityItem activityItem--pending' : 'activityItem'}>
        <Search size={12} className="activityIcon" />
        <span className="activityText">
          Searched for <code className="activityPill">{item.query}</code>
          {item.pending ? (
            <span className="activityMeta"> …</span>
          ) : (
            <span className="activityMeta"> · {item.mode}, {item.hits} {item.hits === 1 ? 'hit' : 'hits'}</span>
          )}
        </span>
      </li>
    );
  }
  const { citation } = step;
  const label = citation.result.heading_path || citation.result.source_filename || citation.result.chunk_id;
  const pages =
    citation.result.page_start != null
      ? citation.result.page_end != null && citation.result.page_end !== citation.result.page_start
        ? `p. ${citation.result.page_start}\u2013${citation.result.page_end}`
        : `p. ${citation.result.page_start}`
      : null;
  return (
    <li className="activityItem">
      <button
        type="button"
        className={selected ? 'activityRowButton activityRowButton--selected' : 'activityRowButton'}
        onClick={() => onSelectCitation?.(citation)}
      >
        <FileText size={12} className="activityIcon" />
        <span className="activityText">
          Read <code className="activityPill">{label}</code>
          {pages ? <span className="activityMeta"> · {pages}</span> : null}
        </span>
      </button>
    </li>
  );
}

function ActivityTrace({
  searches,
  citations,
  selectCitation,
  selectedChunkId,
  live,
}: {
  searches?: ActivitySearchItem[];
  citations?: ChatCitationResult[];
  selectCitation?: (citation: ChatCitationResult) => void;
  selectedChunkId?: string;
  live?: boolean;
}) {
  const steps: ActivityStep[] = [
    ...(searches || []).map((item): ActivityStep => ({ kind: 'search', item })),
    ...(citations || []).map((citation): ActivityStep => ({ kind: 'source', citation })),
  ];
  if (!steps.length) return null;

  const list = (
    <ul className="activityList">
      {steps.map((step, i) => (
        <ActivityStepRow
          key={i}
          step={step}
          onSelectCitation={selectCitation}
          selected={step.kind === 'source' && step.citation.result.chunk_id === selectedChunkId}
        />
      ))}
    </ul>
  );

  if (live) {
    return <div className="activityTrace activityTrace--live">{list}</div>;
  }

  const searchCount = searches?.length || 0;
  const sourceCount = citations?.length || 0;
  const summaryParts: string[] = [];
  if (searchCount) summaryParts.push(`Searched ${searchCount} ${searchCount === 1 ? 'query' : 'queries'}`);
  if (sourceCount) summaryParts.push(`reviewed ${sourceCount} ${sourceCount === 1 ? 'source' : 'sources'}`);

  return (
    <details className="activityDisclosure">
      <summary>{summaryParts.join(' and ') || 'Activity'}</summary>
      {list}
    </details>
  );
}

function TraceView({ events }: { events: StreamEvent[] }) {
  const [expanded, setExpanded] = useState(false);
  if (!events.length) return null;
  return (
    <div className={expanded ? 'llmTrace llmTrace--expanded' : 'llmTrace'}>
      <div className="llmTraceHeader">
        <Terminal size={12} />LLM trace
        <button
          type="button"
          className="traceExpandButton"
          onClick={() => setExpanded((value) => !value)}
          title={expanded ? 'Collapse content blocks' : 'Expand to see full contents'}
        >
          {expanded ? <><Minimize2 size={12} />Collapse</> : <><Maximize2 size={12} />Expand full</>}
        </button>
      </div>
      {events.map((ev, index) => {
        if (ev.event === 'llm_request') {
          return (
            <details className="traceEntry traceRequest" key={index} open={expanded}>
              <summary>
                <span className="traceBadge req">Request</span>
                <span className="traceMeta">turn {ev.turn ?? 0} · {ev.model || 'model'} · {ev.tools && ev.tools.length ? `tools: ${ev.tools.join(', ')}` : 'no tools'}</span>
              </summary>
              <div className="traceMessages">
                {(ev.messages || []).map((message, mi) => {
                  const calls = message.tool_calls
                    ?.map((tc) => `${tc.function?.name || 'tool'}(${tc.function?.arguments || ''})`)
                    .join('\n');
                  return (
                    <div className={`traceMsg traceRole--${message.role}`} key={mi}>
                      <span className="traceRole">{message.role}{message.name ? ` · ${message.name}` : ''}</span>
                      {Array.isArray(message.content) ? (
                        message.content.map((part, pi) =>
                          part.type === 'image_url' ? (
                            <span className="traceContent traceImagePart" key={pi}>{part.image_url.url}</span>
                          ) : (
                            <pre className="traceContent" key={pi}>{part.text}</pre>
                          ),
                        )
                      ) : message.content ? (
                        <pre className="traceContent">{message.content}</pre>
                      ) : null}
                      {calls ? <pre className="traceContent traceToolCalls">{calls}</pre> : null}
                    </div>
                  );
                })}
              </div>
            </details>
          );
        }
        if (ev.event === 'llm_response') {
          const tokens = ev.usage && typeof ev.usage.total_tokens === 'number' ? ev.usage.total_tokens : null;
          const calls = ev.tool_calls?.map((tc) => `${tc.name || 'tool'}(${JSON.stringify(tc.arguments ?? {})})`).join('\n');
          return (
            <details className="traceEntry traceResponse" key={index} open={expanded || !ev.tool_calls?.length}>
              <summary>
                <span className="traceBadge res">Response</span>
                <span className="traceMeta">turn {ev.turn ?? 0} · {ev.model || 'model'}{ev.tool_calls?.length ? ` · ${ev.tool_calls.length} tool call(s)` : ''}{tokens != null ? ` · ${tokens} tok` : ''}</span>
              </summary>
              {ev.content ? <pre className="traceContent">{ev.content}</pre> : null}
              {calls ? <pre className="traceContent traceToolCalls">{calls}</pre> : null}
            </details>
          );
        }
        if (ev.event === 'tool_call') {
          return (
            <details className="traceEntry traceTool" key={index} open={expanded}>
              <summary>
                <span className="traceBadge tool">Tool · {ev.name || 'tool'}</span>
                <span className="traceMeta">{JSON.stringify(ev.arguments ?? {})}</span>
              </summary>
              <pre className="traceContent">{JSON.stringify(ev.output, null, 2)}</pre>
            </details>
          );
        }
        return (
          <div className="traceEntry traceSearch" key={index}>
            <span className={ev.event === 'search_done' ? 'traceBadge search done' : 'traceBadge search'}>{ev.event === 'search_done' ? 'search done' : 'searching'}</span>
            <span className="traceMeta">{ev.query}{ev.event === 'search_done' ? ` · ${ev.mode}, ${ev.hits} hits` : ' …'}</span>
          </div>
        );
      })}
    </div>
  );
}

// Memoized per-turn chat bubble. Historical turns keep a stable `turn` object
// reference (new turns are only ever appended), so as long as the callback/selection
// props stay stable too, React can skip re-rendering (and re-parsing Markdown for)
// every past turn whenever unrelated App state changes, e.g. each composer keystroke.
const ChatTurn = React.memo(function ChatTurn({
  turn,
  selectCitation,
  selectedChunkId,
  showTrace,
}: {
  turn: SessionTurn;
  selectCitation: (citation: ChatCitationResult) => void;
  selectedChunkId?: string;
  showTrace: boolean;
}) {
  if (turn.role === 'user') {
    return (
      <article className="chatMessage userMessage">
        <p>{turn.content}</p>
      </article>
    );
  }
  return (
    <article className="chatMessage assistantMessage">
      <span>
        VERA{turn.mode_label ? ` · ${turn.mode_label}` : ''}{turn.llm ? ` · ${turn.llm.model}` : ''}
      </span>
      <ActivityTrace
        searches={turn.searches}
        citations={turn.citations}
        selectCitation={selectCitation}
        selectedChunkId={selectedChunkId}
      />
      {turn.answer_mode === 'retrieval' ? <div className="noteBanner">This provider does not support tool-calling, so VERA used a single retrieval pass instead of agentic search.</div> : null}
      {turn.citations && turn.citations.length ? (
        renderAnswerWithCitations(turn.content, turn.citations, selectCitation)
      ) : (
        <div className="markdownBody"><Markdown remarkPlugins={[remarkGfm]}>{turn.content}</Markdown></div>
      )}
      {showTrace && turn.trace?.length ? <TraceView events={turn.trace} /> : null}
    </article>
  );
});

function ProviderManager({
  providers,
  activeProviderId,
  activeModel,
  activeModeId,
  onPersist,
  onRefresh,
  onClose,
}: {
  providers: ProviderProfile[];
  activeProviderId: string;
  activeModel: string;
  activeModeId: string;
  onPersist: (next: AppSettings) => Promise<AppSettings>;
  onRefresh: () => Promise<AppSettings>;
  onClose: () => void;
}) {
  const [list, setList] = useState<ProviderProfile[]>(providers);
  const [activeId, setActiveId] = useState(activeProviderId);
  const [activeModelLocal, setActiveModelLocal] = useState(activeModel);
  const [selectedId, setSelectedId] = useState<string>(providers[0]?.id ?? '');
  const [apiKeyInput, setApiKeyInput] = useState('');
  const [modelInput, setModelInput] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [availableModels, setAvailableModels] = useState<string[]>([]);

  const selected = list.find((profile) => profile.id === selectedId) ?? null;
  const enabledModels = new Set(selected?.models ?? []);
  const modelOptions = Array.from(new Set([...(selected?.models ?? []), ...availableModels])).sort((a, b) =>
    a.localeCompare(b),
  );

  function settingsPayload(overrides?: Partial<AppSettings>): AppSettings {
    const nextList = overrides?.providers ?? list;
    const nextActiveId = overrides?.active_provider_id ?? activeId;
    const activeProfile = nextList.find((profile) => profile.id === nextActiveId);
    const requestedModel = overrides?.active_model ?? activeModelLocal;
    const nextActiveModel =
      activeProfile && activeProfile.models.includes(requestedModel)
        ? requestedModel
        : activeProfile?.models[0] ?? '';
    return {
      providers: nextList,
      active_provider_id: activeProfile ? nextActiveId : '',
      active_model: nextActiveModel,
      active_mode_id: overrides?.active_mode_id ?? activeModeId,
    };
  }

  function updateSelected(patch: Partial<ProviderProfile>) {
    setList((prev) => prev.map((profile) => (profile.id === selectedId ? { ...profile, ...patch } : profile)));
  }

  function toggleModel(model: string) {
    if (!selected) return;
    const next = enabledModels.has(model)
      ? selected.models.filter((value) => value !== model)
      : [...selected.models, model];
    updateSelected({ models: next });
  }

  function addManualModel() {
    const model = modelInput.trim();
    if (!selected || !model) return;
    if (!selected.models.includes(model)) {
      updateSelected({ models: [...selected.models, model] });
    }
    setModelInput('');
    setMessage(`Added model ${model}`);
  }

  function addProvider(preset?: ProviderPreset) {
    const profile: ProviderProfile = preset ? { ...preset.value, id: newProviderId() } : emptyProvider();
    setList((prev) => [...prev, profile]);
    setSelectedId(profile.id);
    setApiKeyInput('');
    setModelInput('');
    setAvailableModels([]);
    setMessage(`Added ${providerDisplayName(profile)}`);
  }

  function deleteProvider(id: string) {
    setList((prev) => prev.filter((profile) => profile.id !== id));
    if (activeId === id) {
      setActiveId('');
      setActiveModelLocal('');
    }
    if (selectedId === id) setSelectedId('');
    setMessage('Provider removed (Save to apply)');
  }

  function setAsActive(profile: ProviderProfile) {
    if (activeId === profile.id) {
      setActiveId('');
      setActiveModelLocal('');
      return;
    }
    setActiveId(profile.id);
    setActiveModelLocal(profile.models[0] ?? '');
  }

  async function saveAll(close: boolean) {
    setBusy(true);
    try {
      const saved = await onPersist(settingsPayload());
      setList(saved.providers);
      setActiveId(saved.active_provider_id);
      setActiveModelLocal(saved.active_model || '');
      setMessage('Settings saved');
      if (close) onClose();
    } finally {
      setBusy(false);
    }
  }

  async function saveKey() {
    if (!selected) return;
    if (!apiKeyInput.trim()) {
      setMessage('Enter an API key first');
      return;
    }
    setBusy(true);
    try {
      await onPersist(settingsPayload());
      const result = await window.vera.saveApiKey(selected.base_url, apiKeyInput.trim());
      if (!result.ok) {
        setMessage(result.error || 'Unable to save API key');
        return;
      }
      setApiKeyInput('');
      const refreshed = await onRefresh();
      setList(refreshed.providers);
      setMessage('API key saved');
    } finally {
      setBusy(false);
    }
  }

  async function clearKey() {
    if (!selected) return;
    setBusy(true);
    try {
      await window.vera.clearApiKey(selected.base_url);
      const refreshed = await onRefresh();
      setList(refreshed.providers);
      setMessage('API key cleared');
    } finally {
      setBusy(false);
    }
  }

  async function fetchModels() {
    if (!selected) return;
    if (!selected.base_url.trim()) {
      setMessage('Set a base URL first');
      return;
    }
    setBusy(true);
    setMessage('Fetching models…');
    try {
      const llm: Record<string, unknown> = {
        provider: selected.provider,
        base_url: selected.base_url,
        api_key_env: selected.api_key_env,
        auth_type: selected.auth_type,
      };
      // Use the just-typed key if present so fetch works before saving.
      if (apiKeyInput.trim()) llm.api_key = apiKeyInput.trim();
      const response = await window.vera.request<{ models: string[] }>({ action: 'list_models', llm });
      if (!response.ok) {
        setAvailableModels([]);
        setMessage(response.error || 'Unable to fetch models');
        return;
      }
      const models = response.result?.models ?? [];
      setAvailableModels(models);
      setMessage(models.length ? `Found ${models.length} models` : 'No models returned');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modalBackdrop" onClick={onClose}>
      <div className="modal providerModal" onClick={(event) => event.stopPropagation()}>
        <header className="modalHeader">
          <h2><Settings size={18} />LLM Providers</h2>
          <button className="iconAction" onClick={onClose} aria-label="Close"><X size={18} /></button>
        </header>

        <div className="providerLayout">
          <aside className="providerList">
            <div className="providerListHead">
              <span>Providers</span>
              <button className="secondaryAction compactAction" onClick={() => addProvider()} disabled={busy}><Plus size={14} />Add</button>
            </div>
            {list.length === 0 ? <p className="mutedText">No providers configured yet.</p> : null}
            {list.map((profile) => (
              <button
                key={profile.id}
                type="button"
                className={profile.id === selectedId ? 'providerRow selected' : 'providerRow'}
                onClick={() => { setSelectedId(profile.id); setApiKeyInput(''); setModelInput(''); setAvailableModels([]); }}
              >
                <span className="providerRowName">
                  {providerDisplayName(profile)}
                  {profile.id === activeId ? <em className="activeTag">Active</em> : null}
                </span>
                <small>{providerTypeLabel(profile.provider)} · {profile.models.length} model{profile.models.length === 1 ? '' : 's'}</small>
              </button>
            ))}
            <div className="presetRow">
              <span>Quick add</span>
              <div className="presetButtons">
                {PROVIDER_PRESETS.map((preset) => (
                  <button key={preset.key} type="button" className="secondaryAction compactAction" onClick={() => addProvider(preset)} disabled={busy}>{preset.label}</button>
                ))}
              </div>
            </div>
          </aside>

          <section className="providerEditor">
            {selected ? (
              <>
                <div className="editorGrid">
                  <label className="field wideField">
                    <span>Display Name</span>
                    <input value={selected.label} onChange={(event) => updateSelected({ label: event.target.value })} placeholder="My Provider" />
                  </label>
                  <label className="field">
                    <span>Type</span>
                    <select value={selected.provider} onChange={(event) => updateSelected({ provider: event.target.value })}>
                      <option value="openai_compatible">OpenAI Compatible</option>
                      <option value="ollama">Ollama</option>
                      <option value="lmstudio">LM Studio</option>
                    </select>
                  </label>
                  <label className="field wideField">
                    <span>Base URL</span>
                    <input value={selected.base_url} onChange={(event) => updateSelected({ base_url: event.target.value })} placeholder="https://api.openai.com/v1" />
                  </label>
                  <label className="field">
                    <span>Auth</span>
                    <select value={selected.auth_type} onChange={(event) => updateSelected({ auth_type: event.target.value })}>
                      <option value="none">None</option>
                      <option value="api_key">API Key</option>
                      <option value="env">Env Var</option>
                      <option value="oauth" disabled>OAuth (soon)</option>
                    </select>
                  </label>
                  <label className="field">
                    <span>API Env</span>
                    <input value={selected.api_key_env} onChange={(event) => updateSelected({ api_key_env: event.target.value })} placeholder="OPENAI_API_KEY" />
                  </label>
                  <label className="field">
                    <span>Temp</span>
                    <input className="numberInput" type="number" min={0} max={2} step={0.1} value={selected.temperature} onChange={(event) => updateSelected({ temperature: Number(event.target.value) })} />
                  </label>
                </div>

                <div className="apiKeyRow">
                  <label className="field apiKeyField">
                    <span>{selected.has_api_key ? 'API Key (saved)' : 'API Key'}</span>
                    <input type="password" value={apiKeyInput} onChange={(event) => setApiKeyInput(event.target.value)} placeholder={selected.has_api_key ? '•••••••• stored' : 'sk-...'} />
                  </label>
                  <button className="secondaryAction" onClick={saveKey} disabled={busy || !apiKeyInput.trim()}><KeyRound size={16} />Save Key</button>
                  <button className="secondaryAction" onClick={clearKey} disabled={busy || !selected.has_api_key}><Trash2 size={16} />Clear</button>
                </div>

                <div className="modelsSection">
                  <div className="modelsHead">
                    <span>Models <em>{selected.models.length} enabled</em></span>
                    <button type="button" className="secondaryAction compactAction" onClick={fetchModels} disabled={busy || !selected.base_url.trim()}><ListChecks size={14} />Fetch models</button>
                  </div>
                  {modelOptions.length ? (
                    <div className="modelChecklist">
                      {modelOptions.map((model) => (
                        <label className="modelCheck" key={model}>
                          <input type="checkbox" checked={enabledModels.has(model)} onChange={() => toggleModel(model)} />
                          <span>{model}</span>
                        </label>
                      ))}
                    </div>
                  ) : (
                    <p className="mutedText">No models yet. Click “Fetch models” or add one manually below.</p>
                  )}
                  <div className="modelAddRow">
                    <input
                      value={modelInput}
                      onChange={(event) => setModelInput(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter') {
                          event.preventDefault();
                          addManualModel();
                        }
                      }}
                      placeholder="Add model id manually (e.g. gpt-4o-mini)"
                    />
                    <button type="button" className="secondaryAction compactAction" onClick={addManualModel} disabled={!modelInput.trim()}><Plus size={14} />Add</button>
                  </div>
                </div>

                <div className="editorActions">
                  <button
                    className={selected.id === activeId ? 'secondaryAction activeNow' : 'secondaryAction'}
                    onClick={() => setAsActive(selected)}
                    disabled={busy || selected.models.length === 0}
                  >
                    <CheckCircle2 size={16} />{selected.id === activeId ? 'Active provider' : 'Set as active'}
                  </button>
                  <button className="secondaryAction danger" onClick={() => deleteProvider(selected.id)} disabled={busy}><Trash2 size={16} />Delete</button>
                </div>
              </>
            ) : (
              <div className="emptyState"><Pencil size={20} />Select a provider to edit, or add a new one.</div>
            )}
          </section>
        </div>

        <footer className="modalFooter">
          <span className="modalMessage">{message}</span>
          <div className="modalFooterActions">
            <button className="secondaryAction" onClick={onClose} disabled={busy}>Cancel</button>
            <button className="primaryAction" onClick={() => void saveAll(true)} disabled={busy}>Save &amp; Close</button>
          </div>
        </footer>
      </div>
    </div>
  );
}

function App() {
  const workspaceRef = useRef<HTMLDivElement | null>(null);
  const [sideView, setSideView] = useState<SideView>('explorer');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [folders, setFolders] = useState<WorkspaceFolderResult[]>([]);
  const [viewerMode, setViewerMode] = useState<'selection' | 'document'>('document');
  const [path, setPath] = useState('');
  const [pdfPath, setPdfPath] = useState('');
  const [outputPath, setOutputPath] = useState('');
  const [query, setQuery] = useState('');
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
  const [convertModel, setConvertModel] = useState('hashing');
  const [convertParser, setConvertParser] = useState('pymupdf');
  const [chunkSize, setChunkSize] = useState(500);
  const [overlap, setOverlap] = useState(75);
  const [storeOriginal, setStoreOriginal] = useState(true);
  const [status, setStatus] = useState('Ready');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [inspect, setInspect] = useState<InspectResult | null>(null);
  const [validation, setValidation] = useState<ValidateResult | null>(null);
  const [convertResult, setConvertResult] = useState<ConvertResult | null>(null);
  const [exportResult, setExportResult] = useState<ExportResult | null>(null);
  const [sourceDocument, setSourceDocument] = useState<SourceDocumentResult | null>(null);
  const [sourceDocumentPath, setSourceDocumentPath] = useState('');
  const [pageNumber, setPageNumber] = useState(1);
  const [pageResult, setPageResult] = useState<PageResult | null>(null);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [selected, setSelected] = useState<SearchResult | null>(null);
  const [selectedFiles, setSelectedFiles] = useState<string[]>([]);
  const [collapsedFolders, setCollapsedFolders] = useState<string[]>([]);
  const [chatAnswer, setChatAnswer] = useState<ChatAnswerResult | null>(null);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [sessionTurns, setSessionTurns] = useState<SessionTurn[]>([]);
  const [streamEvents, setStreamEvents] = useState<StreamEvent[]>([]);
  const [traceEvents, setTraceEvents] = useState<StreamEvent[]>([]);
  const [streamingAnswer, setStreamingAnswer] = useState('');
  const [showTrace, setShowTrace] = useState(() => {
    try {
      return localStorage.getItem('vera.showTrace') === '1';
    } catch {
      return false;
    }
  });
  const threadRef = useRef<HTMLDivElement | null>(null);
  const [sourcePaneWidth, setSourcePaneWidth] = useState(34);
  const [isResizingSource, setIsResizingSource] = useState(false);
  const [sidePanelWidth, setSidePanelWidth] = useState(() => {
    const stored = Number(localStorage.getItem('vera.sidePanelWidth'));
    return stored >= 200 && stored <= 600 ? stored : 300;
  });
  const [isResizingSide, setIsResizingSide] = useState(false);

  // Files to search: the explicitly checked set, or the active document.
  const scopedFiles = useMemo(
    () => (selectedFiles.length > 0 ? selectedFiles : path ? [path] : []),
    [selectedFiles, path],
  );
  const isCorpus = Boolean(
    inspect?.directory || (path && !path.toLowerCase().endsWith('.vera')) || selectedFiles.length > 1,
  );
  const busy = Boolean(busyAction);
  const activeProvider = useMemo(
    () => providers.find((profile) => profile.id === activeProviderId) ?? null,
    [providers, activeProviderId],
  );
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
  const sourceExpanded = sourcePaneWidth >= 58;

  function openSide(view: SideView) {
    setSideView(view);
    setSidebarCollapsed(false);
  }

  function toggleSide(view: SideView) {
    if (sideView === view && !sidebarCollapsed) {
      setSidebarCollapsed(true);
    } else {
      setSideView(view);
      setSidebarCollapsed(false);
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
  }

  function removeFolder(folderPath: string) {
    setFolders((prev) => {
      const next = prev.filter((entry) => entry.path !== folderPath);
      localStorage.setItem('vera.folders', JSON.stringify(next.map((entry) => entry.path)));
      return next;
    });
  }

  async function refreshFolder(folderPath: string) {
    const folder = await window.vera.listFolder(folderPath);
    if (folder) setFolders((prev) => prev.map((entry) => (entry.path === folderPath ? folder : entry)));
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

  function openEntry(entry: FolderEntry) {
    if (entry.type === 'vera') {
      void openTargetPath(entry.path);
    } else {
      setPdfPath(entry.path);
      if (!outputPath.trim()) setOutputPath(defaultVeraPath(entry.path));
      openSide('convert');
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
    const activityWidth = 52;
    setSidePanelWidth(clampSidePanelWidth(clientX - bounds.left - activityWidth));
  }

  function resizeSourcePane(clientX: number) {
    const bounds = workspaceRef.current?.getBoundingClientRect();
    if (!bounds) return;
    const widthFromRight = bounds.right - clientX;
    setSourcePaneWidth(clampSourcePaneWidth((widthFromRight / bounds.width) * 100));
  }

  async function call<T>(payload: Record<string, unknown>, label: string): Promise<T | null> {
    setStatus(label);
    setBusyAction(label);
    setErrorMessage(null);
    try {
      const response = await window.vera.request<T>(payload);
      if (!response.ok) {
        setStatus(response.error || 'Request failed');
        setErrorMessage(response.error || 'Request failed');
        return null;
      }
      setStatus('Ready');
      return (response.result || null) as T | null;
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Request failed';
      setStatus(message);
      setErrorMessage(message);
      return null;
    } finally {
      setBusyAction(null);
    }
  }

  async function openTargetPath(value: string) {
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

  async function chooseOutput() {
    const chosen = await window.vera.saveVera(outputPath.trim() || defaultVeraPath(pdfPath));
    if (chosen) setOutputPath(chosen);
  }

  async function inspectTarget() {
    const result = await call<InspectResult>({ action: 'inspect', path }, 'Inspecting');
    if (result) {
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

  async function searchTarget() {
    const result = await call<SearchResult[]>({
      action: 'search',
      path,
      paths: scopedFiles,
      query,
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

  async function askTarget() {
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
    const llm = {
      provider: provider.provider,
      model: activeModel,
      base_url: provider.base_url,
      api_key_env: provider.api_key_env,
      auth_type: provider.auth_type,
      temperature: provider.temperature,
    };

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

    // Optimistically append the user turn to the thread.
    const userTurn: SessionTurn = { role: 'user', content: query, timestamp: Date.now() };
    const nextTurns = [...sessionTurns, userTurn];
    setSessionTurns(nextTurns);
    setQuery('');

    // Set up streaming event listener before firing the request.
    setStreamEvents([]);
    setTraceEvents([]);
    setStreamingAnswer('');
    // Collect every trace event locally too, so it survives even if the backend
    // response doesn't echo a `trace` array (e.g. an older sidecar process).
    const collectedTrace: StreamEvent[] = [];
    const offEvents = window.vera.onAnswerEvent((ev) => {
      collectedTrace.push(ev);
      setTraceEvents((prev) => [...prev, ev]);
      if (ev.event === 'search_start') {
        setStreamEvents((prev) => [...prev, ev]);
      } else if (ev.event === 'search_done') {
        setStreamEvents((prev) => {
          const revIdx = [...prev].reverse().findIndex((e) => e.event === 'search_start' && e.query === ev.query);
          if (revIdx >= 0) {
            const idx = prev.length - 1 - revIdx;
            return prev.map((e, i) => i === idx ? ev : e);
          }
          return [...prev, ev];
        });
      } else if (ev.event === 'answer_delta') {
        setStreamingAnswer((prev) => prev + (ev.text ?? ''));
      } else if (ev.event === 'answer_reset') {
        setStreamingAnswer('');
      }
    });

    const result = await call<ChatAnswerResult>({
      action: 'answer',
      path,
      paths: scopedFiles,
      prompt: query,
      mode_id: activeModeId || activeMode?.id || '',
      history,
      prior_citations: priorCitations,
      llm,
    }, 'Asking');
    offEvents();
    setStreamEvents([]);
    setTraceEvents([]);
    setStreamingAnswer('');
    if (result) {
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
        answer_mode: result.answer_mode,
        mode_label: result.mode_label,
        trace: turnTrace,
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
        source_path: path,
        turns: withAssistant.map(stripTrace),
        created_at: activeSessionId ? (sessions.find((s) => s.id === sid)?.created_at ?? now) : now,
        updated_at: now,
      };
      if (!activeSessionId) setActiveSessionId(sid);
      const saved = await window.vera.saveSession(session);
      setSessions(saved);
    } else {
      // Roll back optimistic user turn on failure.
      setSessionTurns(sessionTurns);
      setQuery(query);
    }
  }

  async function newSession() {
    setChatAnswer(null);
    setSessionTurns([]);
    setActiveSessionId(null);
    setResults([]);
    setSelected(null);
    setQuery('');
  }

  async function loadSession(session: Session) {
    setActiveSessionId(session.id);
    // Re-attach any in-memory traces captured earlier this app session.
    const hydratedTurns = session.turns.map((turn) => {
      if (turn.role !== 'assistant') return turn;
      const trace = traceMemory.get(traceKey(session.id, turn.timestamp));
      return trace ? { ...turn, trace } : turn;
    });
    setSessionTurns(hydratedTurns);
    // Restore the source document FIRST so any stale source is cleared before we
    // select a cited result. Selecting first would race with openTargetPath, which
    // resets sourceDocument to null and blanks the viewer.
    const sessionPath = session.source_path;
    if (sessionPath && sessionPath !== path) {
      await openTargetPath(sessionPath);
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

  async function selectActiveMode(modeId: string) {
    setModePickerOpen(false);
    setActiveModeId(modeId);
    await persistSettings({ providers, active_provider_id: activeProviderId, active_model: activeModel, active_mode_id: modeId });
  }

  async function convertPdf() {
    const output = outputPath.trim() || defaultVeraPath(pdfPath);
    if (!output) {
      setStatus('Choose an output path');
      setErrorMessage('Choose an output path');
      return;
    }
    setOutputPath(output);
    const result = await call<ConvertResult>({
      action: 'convert',
      input: pdfPath,
      output,
      model: convertModel,
      parser: convertParser,
      chunk_size: chunkSize,
      overlap,
      store_original: storeOriginal,
    }, 'Converting PDF');
    if (result) {
      setConvertResult(result);
      updateTargetPath(result.output);
      openSide('info');
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
      setFolders(loaded.filter((entry): entry is WorkspaceFolderResult => entry !== null));
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

  // Auto-scroll thread to bottom when new turns arrive.
  useEffect(() => {
    if (threadRef.current) {
      threadRef.current.scrollTo({ top: threadRef.current.scrollHeight, behavior: 'smooth' });
    }
  }, [sessionTurns.length]);

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

  return (
    <div className="appShell">
      <div className="appBody" ref={workspaceRef} style={{ '--source-pane-width': `${sourcePaneWidth}%`, '--side-panel-width': `${sidePanelWidth}px` } as CSSProperties}>
        <nav className="activityBar">
          <div className="activityTop">
            <button className={!sidebarCollapsed && sideView === 'explorer' ? 'activityBtn active' : 'activityBtn'} onClick={() => toggleSide('explorer')} title="Explorer" aria-label="Explorer"><Files size={22} /></button>
            <button className={!sidebarCollapsed && sideView === 'chats' ? 'activityBtn active' : 'activityBtn'} onClick={() => toggleSide('chats')} title="Chats" aria-label="Chats"><MessageSquareText size={22} /></button>
            <button className={!sidebarCollapsed && sideView === 'search' ? 'activityBtn active' : 'activityBtn'} onClick={() => toggleSide('search')} title="Search" aria-label="Search"><Search size={22} /></button>
            <button className={!sidebarCollapsed && sideView === 'convert' ? 'activityBtn active' : 'activityBtn'} onClick={() => toggleSide('convert')} title="Convert PDF" aria-label="Convert PDF"><FileInput size={22} /></button>
            <button className={!sidebarCollapsed && sideView === 'info' ? 'activityBtn active' : 'activityBtn'} onClick={() => toggleSide('info')} title="Document Info" aria-label="Document Info"><Info size={22} /></button>
          </div>
          <div className="activityBottom">
            <button className="activityBtn" onClick={() => setSettingsOpen(true)} title="LLM Providers" aria-label="LLM Providers"><Settings size={22} /></button>
          </div>
        </nav>

        {!sidebarCollapsed ? (
          <aside className="sidePanel">
            <div className="sidePanelHeader">
              <span className="sidePanelTitle">
                {sideView === 'explorer' ? 'Explorer' : sideView === 'chats' ? 'Chats' : sideView === 'search' ? 'Search' : sideView === 'convert' ? 'Convert PDF' : 'Document'}
              </span>
              <div className="sidePanelActions">
                {sideView === 'explorer' ? (
                  <>
                    <button className="ghostIcon" onClick={() => void addFolder()} title="Open folder"><FolderOpen size={15} /></button>
                    <button className="ghostIcon" onClick={async () => { const f = await window.vera.pickArchive(); if (f) void openTargetPath(f); }} title="Open .vera file"><FileSearch size={15} /></button>
                  </>
                ) : null}
                {sideView === 'chats' ? (
                  <button className="ghostIcon" onClick={() => void newSession()} title="New chat"><Plus size={16} /></button>
                ) : null}
                <button className="ghostIcon" onClick={() => setSidebarCollapsed(true)} title="Hide sidebar"><PanelLeftClose size={15} /></button>
              </div>
            </div>
            <div className="sidePanelBody">
              {sideView === 'explorer' ? (
                folders.length === 0 ? (
                  <div className="sideEmpty">
                    <Folder size={28} />
                    <p>No folders open yet.</p>
                    <button className="sidePrimary" onClick={() => void addFolder()}><FolderOpen size={15} />Open Folder</button>
                  </div>
                ) : (
                  <div className="explorerTree">
                    {folders.map((folder) => (
                      <section className="folderGroup" key={folder.path}>
                        <div className="folderGroupHead" title={folder.path}>
                          <button
                            className="folderGroupToggle"
                            onClick={() => toggleFolderCollapsed(folder.path)}
                            title={collapsedFolders.includes(folder.path) ? 'Expand' : 'Collapse'}
                          >
                            {collapsedFolders.includes(folder.path) ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
                            <Folder size={14} />
                            <span className="folderGroupName">{folder.name}</span>
                          </button>
                          <button className="ghostIcon tiny" onClick={() => void refreshFolder(folder.path)} title="Refresh"><RotateCw size={12} /></button>
                          <button className="ghostIcon tiny" onClick={() => removeFolder(folder.path)} title="Close folder"><X size={12} /></button>
                        </div>
                        {collapsedFolders.includes(folder.path) ? null : folder.entries.length === 0 ? (
                          <p className="folderEmpty">No .vera or .pdf files</p>
                        ) : (
                          folder.entries.map((entry) => (
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
                                title={entry.relativePath}
                              >
                                {entry.type === 'vera' ? <FileSearch size={14} className="fileRowIcon vera" /> : <FileText size={14} className="fileRowIcon pdf" />}
                                <span className="fileRowName">{entry.relativePath}</span>
                              </button>
                            </div>
                          ))
                        )}
                      </section>
                    ))}
                  </div>
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
                      value={query}
                      rows={3}
                      onChange={(event) => setQuery(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
                          event.preventDefault();
                          void searchTarget();
                        }
                      }}
                      placeholder="Search the selected document…"
                    />
                    {selectedFiles.length > 0 ? (
                      <div className="searchScope">
                        <span>{selectedFiles.length === 1 ? '1 document selected' : `${selectedFiles.length} documents selected`}</span>
                        <button type="button" onClick={() => setSelectedFiles([])} title="Clear selection">Clear</button>
                      </div>
                    ) : null}
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
                    <button className="sidePrimary" onClick={searchTarget} disabled={scopedFiles.length === 0 || !query.trim() || busy}><Search size={15} />Search</button>
                  </div>
                  <div className="searchResults">
                    {results.length === 0 ? (
                      <p className="sideMuted">{path ? 'No results yet.' : 'Open a document first.'}</p>
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
                  <button className="secondaryAction" onClick={choosePdf} disabled={busy}><FolderOpen size={16} />Choose PDF</button>
                  <label className="field">
                    <span>Output</span>
                    <div className="pathInput">
                      <FileSearch size={16} />
                      <input value={outputPath} onChange={(event) => setOutputPath(event.target.value)} placeholder="C:\\docs\\manual.vera" />
                    </div>
                  </label>
                  <button className="secondaryAction" onClick={chooseOutput} disabled={busy}><FolderOpen size={16} />Save As</button>
                  <div className="convertGrid">
                    <label className="miniField">
                      <span>Parser</span>
                      <select value={convertParser} onChange={(event) => setConvertParser(event.target.value)}>
                        <option value="pymupdf">PyMuPDF</option>
                        <option value="docling">Docling</option>
                      </select>
                    </label>
                    <label className="miniField">
                      <span>Model</span>
                      <select value={convertModel} onChange={(event) => setConvertModel(event.target.value)}>
                        <option value="hashing">Hashing</option>
                        <option value="openai">OpenAI</option>
                      </select>
                    </label>
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
                  <button className="sidePrimary" onClick={convertPdf} disabled={!pdfPath.trim() || busy}><RefreshCw size={16} />Convert</button>
                  {convertResult && <p className="sideMuted">Created {convertResult.output}</p>}
                </div>
              ) : null}

              {sideView === 'info' ? (
                <div className="infoView">
                  {path ? (
                    <>
                      <div className="infoActions">
                        <button className="secondaryAction" onClick={inspectTarget} disabled={!path.trim() || busy}><ShieldCheck size={15} />Inspect</button>
                        <button className="secondaryAction" onClick={validateTarget} disabled={!path.trim() || isCorpus || busy}><CheckCircle2 size={15} />Validate</button>
                        <button className="secondaryAction" onClick={exportSource} disabled={!path.trim() || isCorpus || busy}><Download size={15} />Export</button>
                      </div>
                      <dl className="infoList">
                        <div><dt>Format</dt><dd>{inspect ? `${inspect.format_name || 'VERA'} ${inspect.format_version || ''}` : '-'}</dd></div>
                        <div><dt>Source</dt><dd>{inspect?.source || inspect?.directory || '-'}</dd></div>
                        <div><dt>Pages</dt><dd>{inspect?.pages ?? '-'}</dd></div>
                        <div><dt>Chunks</dt><dd>{inspect?.chunks ?? '-'}</dd></div>
                        <div><dt>Model</dt><dd>{inspect?.default_embedding_model || inspect?.embedding_models?.join(', ') || '-'}</dd></div>
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
            onDoubleClick={() => setSidePanelWidth(300)}
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
            <button className="ghostIcon" onClick={() => setSidebarCollapsed((value) => !value)} title="Toggle sidebar" aria-label="Toggle sidebar"><PanelLeftClose size={16} /></button>
            <div className="brand">
              <span className="brandMark"><FileSearch size={15} /></span>
              <span className="brandName">VERA</span>
            </div>
            <span className="centerDoc" title={path}>{path ? (path.split(/[\\/]/).pop() || path) : 'No document selected'}</span>
            <span className={busyAction ? 'centerStatus busy' : 'centerStatus'}>{busyAction ? <><span className="statusDot" />{busyAction}</> : status}</span>
          </header>

          {errorMessage ? <div className="errorBanner centerBanner">{errorMessage}</div> : null}

          <div className={sessionTurns.length > 0 ? 'chatPanel chatPanel--active' : 'chatPanel chatPanel--empty'}>
              {sessionTurns.length > 0 ? (
                <div className="chatThread" ref={threadRef}>
                  {sessionTurns.map((turn, idx) => (
                    <ChatTurn
                      key={idx}
                      turn={turn}
                      selectCitation={stableSelectCitation}
                      selectedChunkId={selected?.chunk_id}
                      showTrace={showTrace}
                    />
                  ))}
                  {busy && (streamEvents.length > 0 || streamingAnswer) ? (
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
                    </article>
                  ) : null}
                </div>
              ) : (
                <div className="chatEmptyState">
                  <p>Ready when you are.</p>
                </div>
              )}
              <div className="askComposerWrap">
                <div className="askComposer">
                  <div className="askInputRow">
                    <textarea
                      className="askInput"
                      value={query}
                      rows={1}
                      onChange={(event) => setQuery(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' && !event.shiftKey) {
                          event.preventDefault();
                          void askTarget();
                        }
                      }}
                      placeholder={sessionTurns.length > 0 ? 'Follow up…' : 'Ask anything'}
                    />
                    <button className="askSendButton" onClick={askTarget} disabled={!path.trim() || !query.trim() || busy} title="Send (Enter)">
                      {busy ? <span className="askSpinner" /> : <Send size={16} />}
                    </button>
                  </div>
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
                        onClick={() => setModelPickerOpen((open) => !open)}
                      >
                        <Sparkles size={14} />
                        <span>{activeProvider && activeModel ? `${providerDisplayName(activeProvider)} · ${activeModel}` : 'Select model'}</span>
                        <ChevronDown size={14} />
                      </button>
                      {modelPickerOpen ? (
                        <>
                          <div className="modelPickerBackdrop" onClick={() => setModelPickerOpen(false)} />
                          <div className="modelPickerMenu" role="menu">
                            {providers.length === 0 ? (
                              <div className="modelPickerEmpty">No providers yet — add one below.</div>
                            ) : null}
                            {providers.map((profile) => (
                              <div className="modelPickerGroup" key={profile.id}>
                                <div className="modelPickerGroupLabel">{providerDisplayName(profile)}</div>
                                {profile.models.length === 0 ? (
                                  <div className="modelPickerEmpty">No models enabled</div>
                                ) : (
                                  profile.models.map((model) => (
                                    <button
                                      type="button"
                                      key={`${profile.id}-${model}`}
                                      className={profile.id === activeProviderId && model === activeModel ? 'modelOption active' : 'modelOption'}
                                      onClick={() => void selectActiveModel(profile.id, model)}
                                    >
                                      <span>{model}</span>
                                    </button>
                                  ))
                                )}
                              </div>
                            ))}
                            <div className="modelPickerSep" />
                            <button
                              type="button"
                              className="modelOption manageOption"
                              onClick={() => {
                                setModelPickerOpen(false);
                                setSettingsOpen(true);
                              }}
                            >
                              <Settings size={14} />
                              <span>Manage providers…</span>
                            </button>
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
            </div>
        </main>

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
                  <button className={viewerMode === 'selection' ? 'active' : ''} onClick={() => setViewerMode('selection')} title="Show chunk debug data">Details</button>
                  <button className={viewerMode === 'document' ? 'active' : ''} onClick={() => { setViewerMode('document'); if (!sourceDocument && selectedSourcePath) void loadSourceDocument(selectedSourcePath, false); }} title="Show full document">Document</button>
                </div>
              ) : null}
              <button className="ghostIcon" onClick={() => setSourcePaneWidth(sourceExpanded ? 34 : 64)} title={sourceExpanded ? 'Restore viewer' : 'Expand viewer'} aria-label={sourceExpanded ? 'Restore viewer' : 'Expand viewer'}>
                {sourceExpanded ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
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
                highlightRegions={selected && sourceDocumentPath === selectedSourcePath ? (selected.regions || EMPTY_REGIONS) : EMPTY_REGIONS}
                targetPage={selected && sourceDocumentPath === selectedSourcePath ? selectedTargetPage : null}
              />
            </div>
          ) : sourceDocument ? (
            <div className="unsupportedSource">
              <strong>{sourceDocument.filename}</strong>
              <span>{sourceDocument.mime_type}</span>
            </div>
          ) : (
            <div className="emptyState">
              <FileSearch size={30} />
              <p>Select a citation or open a document to preview it here.</p>
            </div>
          )}
        </aside>
      </div>
      <footer className="statusbar">
        <span className="statusPath">{path || 'No file open'}</span>
        <span>Pages: {inspect?.pages ?? '-'}</span>
        <span>Chunks: {inspect?.chunks ?? '-'}</span>
        <span>Files: {inspect?.file_count ?? '-'}</span>
        <span>Model: {inspect?.default_embedding_model || inspect?.embedding_models?.join(', ') || '-'}</span>
      </footer>
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
    </div>
  );
}

createRoot(document.getElementById('root')!).render(<App />);
