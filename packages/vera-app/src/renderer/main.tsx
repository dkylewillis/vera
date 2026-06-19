import React, { type CSSProperties, useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import * as pdfjsLib from 'pdfjs-dist';
import pdfWorkerUrl from 'pdfjs-dist/build/pdf.worker.mjs?url';
import {
  CheckCircle2,
  Download,
  FileInput,
  FileSearch,
  FolderOpen,
  MessageSquareText,
  RefreshCw,
  Search,
  Send,
  ShieldCheck,
  TerminalSquare,
} from 'lucide-react';
import type { ChatAnswerResult, ChatCitationResult, ConvertResult, ExportResult, InspectResult, PageResult, RegionResult, SearchResult, SourceDocumentResult, ValidateResult } from './types';
import './styles.css';

type ActiveTab = 'ask' | 'search' | 'viewer' | 'convert' | 'details';

const EMPTY_REGIONS: RegionResult[] = [];

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

function PdfSourceViewer({
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
  const renderedSourceRef = useRef('');
  const [scale, setScale] = useState(1.25);
  const [error, setError] = useState<string | null>(null);
  const [pageCount, setPageCount] = useState(0);
  const [rendering, setRendering] = useState(false);
  const highlightKey = useMemo(() => JSON.stringify(highlightRegions), [highlightRegions]);

  useEffect(() => {
    let canceled = false;

    async function renderPdfPages() {
      setError(null);
      setRendering(true);
      try {
        const bytes = await fetch(source.data_url).then((response) => response.arrayBuffer());
        const pdf = await pdfjsLib.getDocument({ data: new Uint8Array(bytes) }).promise;
        if (canceled) return;
        setPageCount(pdf.numPages);
        const container = pagesRef.current;
        if (!container) return;
        if (renderedSourceRef.current !== source.data_url) {
          container.scrollTop = 0;
          renderedSourceRef.current = source.data_url;
        }
        container.replaceChildren();
        for (let pageIndex = 1; pageIndex <= pdf.numPages; pageIndex += 1) {
          if (canceled) return;
          const page = await pdf.getPage(pageIndex);
          const viewport = page.getViewport({ scale });
          const pageShell = document.createElement('article');
          pageShell.className = 'pdfPage';
          pageShell.dataset.pageNumber = String(pageIndex);
          const label = document.createElement('span');
          label.textContent = `Page ${pageIndex}`;
          const pageSurface = document.createElement('div');
          pageSurface.className = 'pdfPageSurface';
          const canvas = document.createElement('canvas');
          const highlightLayer = document.createElement('div');
          highlightLayer.className = 'pdfHighlightLayer';
          const textLayerContainer = document.createElement('div');
          textLayerContainer.className = 'textLayer';
          const context = canvas.getContext('2d');
          if (!context) continue;
          canvas.width = Math.floor(viewport.width);
          canvas.height = Math.floor(viewport.height);
          pageSurface.style.width = `${Math.floor(viewport.width)}px`;
          pageSurface.style.height = `${Math.floor(viewport.height)}px`;
          for (const region of highlightRegions.filter((entry) => entry.page_number === pageIndex && entry.bbox?.length === 4)) {
            const box = document.createElement('div');
            box.className = 'pdfHighlightBox';
            Object.assign(box.style, regionStyle(region));
            highlightLayer.append(box);
          }
          pageSurface.append(canvas, highlightLayer, textLayerContainer);
          pageShell.append(label, pageSurface);
          container.append(pageShell);
          await page.render({ canvas, canvasContext: context, viewport }).promise;
          const textLayer = new pdfjsLib.TextLayer({
            textContentSource: page.streamTextContent(),
            container: textLayerContainer,
            viewport,
          });
          await textLayer.render();
        }
        if (!canceled && targetPage) {
          const target = container.querySelector<HTMLElement>(`[data-page-number="${targetPage}"]`);
          if (target) {
            container.scrollTo({ top: target.offsetTop, behavior: renderedSourceRef.current === source.data_url ? 'smooth' : 'auto' });
          }
        }
      } catch (renderError) {
        if (!canceled) setError(renderError instanceof Error ? renderError.message : 'Unable to render PDF');
      } finally {
        if (!canceled) setRendering(false);
      }
    }

    renderPdfPages();

    return () => {
      canceled = true;
    };
  }, [highlightKey, scale, source.data_url, targetPage]);

  return (
    <div className={compact ? 'pdfViewer compact' : 'pdfViewer'}>
      <div className="viewerToolbar">
        <span>{rendering ? 'Rendering' : `${pageCount || '-'} pages`}</span>
        <button className="secondaryAction" onClick={() => setScale((value) => Math.max(0.75, value - 0.25))}>Zoom Out</button>
        <button className="secondaryAction" onClick={() => setScale((value) => Math.min(2.5, value + 0.25))}>Zoom In</button>
      </div>
      {error ? <div className="errorBanner">{error}</div> : null}
      <div className="pdfCanvasWrap" ref={pagesRef} />
    </div>
  );
}

function renderAnswerWithCitations(answer: ChatAnswerResult, selectCitation: (citation: ChatCitationResult) => void) {
  const citationById = new Map(answer.citations.map((citation) => [citation.id, citation]));
  return answer.answer.split(/(\[C\d+\])/g).map((part, index) => {
    const id = part.match(/^\[(C\d+)\]$/)?.[1];
    const citation = id ? citationById.get(id) : null;
    if (!citation) return <React.Fragment key={`text-${index}`}>{part}</React.Fragment>;
    return (
      <button className="inlineCitation" key={citation.id} onClick={() => selectCitation(citation)}>
        {part}
      </button>
    );
  });
}

function App() {
  const [activeTab, setActiveTab] = useState<ActiveTab>('ask');
  const [path, setPath] = useState('');
  const [pdfPath, setPdfPath] = useState('');
  const [outputPath, setOutputPath] = useState('');
  const [query, setQuery] = useState('restaurant parking requirements');
  const [mode, setMode] = useState('hybrid');
  const [topK, setTopK] = useState(8);
  const [contextChunks, setContextChunks] = useState(0);
  const [includeFigures, setIncludeFigures] = useState(true);
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
  const [chatAnswer, setChatAnswer] = useState<ChatAnswerResult | null>(null);

  const isCorpus = Boolean(inspect?.directory || (path && !path.toLowerCase().endsWith('.vera')));
  const busy = Boolean(busyAction);

  const citation = useMemo(() => {
    if (!selected) return 'No result selected';
    const source = selected.file || selected.source_filename || 'document';
    return `${source} · p. ${formatPages(selected.page_start, selected.page_end)}`;
  }, [selected]);

  const selectedSourcePath = selected?.file || path;
  const selectedTargetPage = selected?.regions?.find((region) => region.page_number)?.page_number ?? selected?.page_start ?? null;

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

  async function chooseArchive() {
    const chosen = await window.vera.pickArchive();
    if (chosen) updateTargetPath(chosen);
  }

  async function chooseFolder() {
    const chosen = await window.vera.pickFolder();
    if (chosen) updateTargetPath(chosen);
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
      setActiveTab('details');
    }
  }

  async function validateTarget() {
    const result = await call<ValidateResult>({ action: 'validate', path }, 'Validating');
    if (result) {
      setValidation(result);
      setActiveTab('details');
    }
  }

  async function searchTarget() {
    const result = await call<SearchResult[]>({
      action: 'search',
      path,
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
      setActiveTab('search');
    }
  }

  async function askTarget() {
    const result = await call<ChatAnswerResult>({
      action: 'answer',
      path,
      prompt: query,
      mode,
      top_k: topK,
      context_chunks: contextChunks,
      include_figures: includeFigures,
      include_figure_data: includeFigures,
    }, 'Asking');
    if (result) {
      setChatAnswer(result);
      const citedResults = result.citations.map((citation) => citation.result);
      setResults(citedResults);
      if (citedResults[0]) {
        selectSearchResult(citedResults[0]);
      } else {
        setSelected(null);
      }
      setActiveTab('ask');
    }
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
      setActiveTab('details');
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
      if (activateViewer) setActiveTab('viewer');
    }
  }

  function selectSearchResult(result: SearchResult) {
    setSelected(result);
    const resultPath = result.file || path;
    if (resultPath && resultPath !== sourceDocumentPath) {
      void loadSourceDocument(resultPath, false);
    }
  }

  function selectCitation(citation: ChatCitationResult) {
    selectSearchResult(citation.result);
  }

  async function loadPage() {
    const result = await call<PageResult>({ action: 'page', path, page_number: pageNumber }, 'Loading page');
    if (result) {
      setPageResult(result);
      setActiveTab('details');
    }
  }

  return (
    <main className="shell">
      <header className="titlebar">
        <div className="brand">
          <FileSearch size={20} />
          <span>VERA Workbench</span>
        </div>
        <div className="status"><TerminalSquare size={16} />{status}</div>
      </header>

      <section className="workspace">
        <aside className="sidebar">
          <div className="tabs">
            <button className={activeTab === 'ask' ? 'active primaryTab' : 'primaryTab'} onClick={() => setActiveTab('ask')}><MessageSquareText size={15} />Ask</button>
            <button className={activeTab === 'search' ? 'active' : ''} onClick={() => setActiveTab('search')}>Search</button>
            <button className={activeTab === 'viewer' ? 'active' : ''} onClick={() => setActiveTab('viewer')}>Viewer</button>
            <button className={activeTab === 'convert' ? 'active' : ''} onClick={() => setActiveTab('convert')}>Convert</button>
            <button className={activeTab === 'details' ? 'active' : ''} onClick={() => setActiveTab('details')}>Details</button>
          </div>

          {busyAction ? <div className="activityBanner"><span />{busyAction}</div> : null}
          {errorMessage ? <div className="errorBanner">{errorMessage}</div> : null}

          {activeTab !== 'convert' ? (
            <>
              <label className="field">
                <span>Archive or Folder</span>
                <div className="pathInput">
                  <FolderOpen size={16} />
                  <input value={path} onChange={(event) => updateTargetPath(event.target.value)} placeholder="C:\\docs\\manual.vera" />
                </div>
              </label>

              <div className="actions three">
                  <button onClick={chooseArchive} disabled={busy}><FileInput size={16} />File</button>
                  <button onClick={chooseFolder} disabled={busy}><FolderOpen size={16} />Folder</button>
                  <button onClick={inspectTarget} disabled={!path.trim() || busy}><ShieldCheck size={16} />Inspect</button>
              </div>

              <div className="actions two">
                <button onClick={validateTarget} disabled={!path.trim() || isCorpus || busy}><CheckCircle2 size={16} />Validate</button>
                <button onClick={exportSource} disabled={!path.trim() || isCorpus || busy}><Download size={16} />Export</button>
              </div>

              <button className="secondaryAction" onClick={() => loadSourceDocument(path, true)} disabled={!path.trim() || isCorpus || busy}><FileSearch size={16} />Load Source</button>

              {activeTab !== 'ask' ? (
                <label className="field">
                  <span>Query</span>
                  <textarea value={query} onChange={(event) => setQuery(event.target.value)} />
                </label>
              ) : null}

              <div className="splitFields">
                <label className="field">
                  <span>Mode</span>
                  <select value={mode} onChange={(event) => setMode(event.target.value)}>
                    <option value="hybrid">Hybrid</option>
                    <option value="semantic">Semantic</option>
                    <option value="keyword">Keyword</option>
                  </select>
                </label>
                <label className="field">
                  <span>Top K</span>
                  <input className="numberInput" type="number" min={1} max={50} value={topK} onChange={(event) => setTopK(Number(event.target.value))} />
                </label>
              </div>

              <label className="field">
                <span>Context Chunks</span>
                <input className="numberInput" type="number" min={0} max={5} value={contextChunks} onChange={(event) => setContextChunks(Number(event.target.value))} />
              </label>

              <label className="checkField">
                <input type="checkbox" checked={includeFigures} onChange={(event) => setIncludeFigures(event.target.checked)} />
                <span>Figures</span>
              </label>

              {activeTab !== 'ask' ? (
                <button className="primaryAction" onClick={searchTarget} disabled={!path.trim() || !query.trim() || busy}><Search size={16} />Search</button>
              ) : null}
            </>
          ) : (
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
              <button className="secondaryAction" onClick={choosePdf} disabled={busy}><FolderOpen size={16} />Choose PDF</button>

              <label className="field">
                <span>Output</span>
                <div className="pathInput">
                  <FileSearch size={16} />
                  <input value={outputPath} onChange={(event) => setOutputPath(event.target.value)} placeholder="C:\\docs\\manual.vera" />
                </div>
              </label>
              <button className="secondaryAction" onClick={chooseOutput} disabled={busy}><FolderOpen size={16} />Save As</button>

              <div className="splitFields">
                <label className="field">
                  <span>Parser</span>
                  <select value={convertParser} onChange={(event) => setConvertParser(event.target.value)}>
                    <option value="pymupdf">PyMuPDF</option>
                    <option value="docling">Docling</option>
                  </select>
                </label>
                <label className="field">
                  <span>Model</span>
                  <select value={convertModel} onChange={(event) => setConvertModel(event.target.value)}>
                    <option value="hashing">Hashing</option>
                    <option value="openai">OpenAI</option>
                  </select>
                </label>
              </div>

              <div className="splitFields">
                <label className="field">
                  <span>Chunk Size</span>
                  <input className="numberInput" type="number" min={100} max={3000} step={50} value={chunkSize} onChange={(event) => setChunkSize(Number(event.target.value))} />
                </label>
                <label className="field">
                  <span>Overlap</span>
                  <input className="numberInput" type="number" min={0} max={1000} step={25} value={overlap} onChange={(event) => setOverlap(Number(event.target.value))} />
                </label>
              </div>

              <label className="checkField">
                <input type="checkbox" checked={storeOriginal} onChange={(event) => setStoreOriginal(event.target.checked)} />
                <span>Store original PDF</span>
              </label>

              <button className="primaryAction" onClick={convertPdf} disabled={!pdfPath.trim() || busy}><RefreshCw size={16} />Convert</button>
              {convertResult && <p className="note">Created {convertResult.output}</p>}
            </>
          )}

          <section className="metrics">
            <div><span>Pages</span><strong>{inspect?.pages ?? '-'}</strong></div>
            <div><span>Chunks</span><strong>{inspect?.chunks ?? '-'}</strong></div>
            <div><span>Files</span><strong>{inspect?.file_count ?? '-'}</strong></div>
            <div><span>Model</span><strong>{inspect?.default_embedding_model || inspect?.embedding_models?.join(', ') || '-'}</strong></div>
          </section>
        </aside>

        <section className="resultsPane">
          <div className="paneHeader">
            <h1>{activeTab === 'viewer' ? 'Source Viewer' : activeTab === 'ask' ? 'Answer' : 'Results'}</h1>
            <span>{activeTab === 'viewer' ? sourceDocument?.filename || 'No source loaded' : activeTab === 'ask' ? `${chatAnswer?.citations.length ?? 0} citations` : `${results.length} matches`}</span>
          </div>
          {activeTab === 'viewer' ? (
            <div className="sourceViewer">
              {sourceDocument && isPdfSource(sourceDocument) ? (
                <PdfSourceViewer source={sourceDocument} />
              ) : sourceDocument ? (
                <div className="unsupportedSource">
                  <strong>{sourceDocument.filename}</strong>
                  <span>{sourceDocument.mime_type}</span>
                </div>
              ) : (
                <div className="emptyState">Load a source document from a `.vera` archive</div>
              )}
            </div>
          ) : activeTab === 'ask' ? (
            <div className="chatPanel">
              <div className="chatThread">
                {chatAnswer ? (
                  <>
                  <article className="chatMessage userMessage">
                    <span>You</span>
                    <p>{chatAnswer.prompt}</p>
                  </article>
                  <article className="chatMessage assistantMessage">
                    <span>VERA</span>
                    <p>{renderAnswerWithCitations(chatAnswer, selectCitation)}</p>
                  </article>
                  <section className="citationList">
                    {chatAnswer.citations.map((citation) => (
                      <button className={selected?.chunk_id === citation.result.chunk_id ? 'citationCard selected' : 'citationCard'} key={citation.id} onClick={() => selectCitation(citation)}>
                        <strong>{citation.label}</strong>
                        <span>{citation.result.heading_path || citation.result.source_filename || citation.result.chunk_id}</span>
                      </button>
                    ))}
                  </section>
                  </>
                ) : (
                  <div className="emptyState"><MessageSquareText size={20} />Ask a question about the selected archive or folder.</div>
                )}
              </div>
              <div className="askComposer">
                <textarea
                  className="askInput"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  onKeyDown={(event) => {
                    if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
                      event.preventDefault();
                      void askTarget();
                    }
                  }}
                  placeholder="Ask VERA about the selected source..."
                />
                <button className="primaryAction askAction" onClick={askTarget} disabled={!path.trim() || !query.trim() || busy}><Send size={16} />Ask VERA</button>
              </div>
            </div>
          ) : (
            <div className="resultsList">
              {results.map((result) => (
                <button
                  className={selected?.chunk_id === result.chunk_id ? 'result selected' : 'result'}
                  key={`${result.file || result.document_id}-${result.chunk_id}`}
                  onClick={() => selectSearchResult(result)}
                >
                  <span className="resultMeta">{result.score.toFixed(4)} · p. {formatPages(result.page_start, result.page_end)}{result.file ? ` · ${result.file}` : ''}</span>
                  <strong>{result.heading_path || result.source_filename || result.chunk_id}</strong>
                  <span>{result.text}</span>
                </button>
              ))}
            </div>
          )}
        </section>

        <section className="sourcePane">
          <div className="paneHeader">
            <h1>{activeTab === 'details' || activeTab === 'viewer' ? 'Document Details' : 'Source Document'}</h1>
            <span>{activeTab === 'details' || activeTab === 'viewer' ? path || 'No archive selected' : citation}</span>
          </div>
          {activeTab === 'details' || activeTab === 'viewer' ? (
            <article className="sourceDetails">
              <dl>
                <div><dt>Format</dt><dd>{inspect ? `${inspect.format_name || 'VERA'} ${inspect.format_version || ''}` : '-'}</dd></div>
                <div><dt>Source</dt><dd>{inspect?.source || inspect?.directory || '-'}</dd></div>
                <div><dt>Validation</dt><dd>{validation ? (validation.ok ? 'PASS' : 'FAIL') : '-'}</dd></div>
                <div><dt>Issues</dt><dd>{validation?.issues?.length ? validation.issues.join('; ') : '0'}</dd></div>
                <div><dt>Export</dt><dd>{exportResult?.output || '-'}</dd></div>
              </dl>
              {sourceDocument ? (
                <section className="sourceMetaSection">
                  <h2>Source Document</h2>
                  <dl>
                    <div><dt>File</dt><dd>{sourceDocument.filename}</dd></div>
                    <div><dt>Type</dt><dd>{sourceDocument.mime_type}</dd></div>
                    <div><dt>Size</dt><dd>{Math.round(sourceDocument.size / 1024).toLocaleString()} KB</dd></div>
                    <div><dt>Hash</dt><dd>{sourceDocument.hash}</dd></div>
                  </dl>
                </section>
              ) : null}
              <section className="sourceMetaSection">
                <h2>Page Text</h2>
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
                  <p className="mutedText">Load a page to inspect extracted page text.</p>
                )}
              </section>
            </article>
          ) : selected ? (
            <article className="sourceDetails sourceViewerOnly">
              <section className="sourceDocumentSection">
                {sourceDocument && isPdfSource(sourceDocument) && sourceDocumentPath === selectedSourcePath ? (
                  <PdfSourceViewer source={sourceDocument} highlightRegions={selected.regions || []} targetPage={selectedTargetPage} compact />
                ) : (
                  <div className="viewerPlaceholder">
                    <button className="secondaryAction" onClick={() => loadSourceDocument(selectedSourcePath, false)} disabled={!selectedSourcePath.trim() || busy}>
                      <FileSearch size={16} />Load Source With Highlights
                    </button>
                  </div>
                )}
              </section>

              <details className="sourceDisclosure">
                <summary>Passage Text</summary>
                <p>{selected.text}</p>
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
          ) : (
            <div className="emptyState">No source selection yet</div>
          )}
        </section>
      </section>
    </main>
  );
}

createRoot(document.getElementById('root')!).render(<App />);
