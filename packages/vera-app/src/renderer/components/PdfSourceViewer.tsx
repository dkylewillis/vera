import React, { type CSSProperties, useEffect, useMemo, useRef, useState } from 'react';
import * as pdfjsLib from 'pdfjs-dist';
import pdfWorkerUrl from 'pdfjs-dist/build/pdf.worker.mjs?url';
import { Highlighter } from 'lucide-react';
import type { FigureResult, RegionResult, SourceDocumentResult } from '../types';
import { EMPTY_REGIONS } from '../lib/constants';

pdfjsLib.GlobalWorkerOptions.workerSrc = pdfWorkerUrl;

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
  highlightFigures = [],
  compact = false,
  targetPage,
}: {
  source: SourceDocumentResult;
  highlightRegions?: RegionResult[];
  highlightFigures?: FigureResult[];
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
  const highlightKey = useMemo(
    () => JSON.stringify([highlightRegions, highlightFigures]),
    [highlightRegions, highlightFigures],
  );

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
          for (const figure of highlightFigures.filter((item) => item.page_number === pageNum && item.bbox?.length === 4)) {
            const box = document.createElement('div');
            box.className = 'pdfHighlightBox pdfHighlightBox--figure';
            Object.assign(box.style, regionStyle(figure));
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
export const PdfSourceViewer = React.memo(PdfSourceViewerImpl);
