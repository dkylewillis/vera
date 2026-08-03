import React, { type CSSProperties, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import * as pdfjsLib from 'pdfjs-dist';
import pdfWorkerUrl from 'pdfjs-dist/build/pdf.worker.mjs?url';
import {
  ChevronLeft,
  ChevronRight,
  Highlighter,
  Maximize2,
  Scan,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';
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

const PDF_ZOOM_MIN = 0.5;
const PDF_ZOOM_MAX = 2.5;
const PDF_FIT_ZOOM_MIN = 0.25;
const PDF_ZOOM_DEFAULT = 1;
const PDF_ZOOM_STEP = 0.25;
/** Wheel/trackpad delta accumulated before applying one discrete zoom step. */
const PDF_ZOOM_WHEEL_THRESHOLD = 80;
/** Horizontal padding inside `.pdfCanvasWrap` (matches CSS). */
const PDF_CANVAS_PAD_X = 32;
/** Vertical padding inside `.pdfCanvasWrap` (matches CSS). */
const PDF_CANVAS_PAD_Y = 32;
type ZoomMode = 'manual' | 'fit-width' | 'fit-page';

type ScrollAnchor = {
  page: number;
  fraction: number;
};

type PageSize = {
  width: number;
  height: number;
};

function clampPdfZoom(value: number, snap = true): number {
  const clamped = Math.min(PDF_ZOOM_MAX, Math.max(PDF_ZOOM_MIN, value));
  if (!snap) return clamped;
  const steps = Math.round((clamped - PDF_ZOOM_MIN) / PDF_ZOOM_STEP);
  return Math.min(PDF_ZOOM_MAX, Math.max(PDF_ZOOM_MIN, PDF_ZOOM_MIN + steps * PDF_ZOOM_STEP));
}

function clampPdfFitZoom(value: number): number {
  return Math.min(PDF_ZOOM_MAX, Math.max(PDF_FIT_ZOOM_MIN, value));
}

function captureScrollAnchor(container: HTMLElement | null): ScrollAnchor | null {
  if (!container) return null;
  const pages = container.querySelectorAll<HTMLElement>('[data-page-number]');
  if (!pages.length) return null;
  const scrollTop = container.scrollTop;
  for (const page of pages) {
    const top = page.offsetTop;
    const height = Math.max(1, page.offsetHeight);
    if (scrollTop + 1 < top + height) {
      return {
        page: Number(page.dataset.pageNumber) || 1,
        fraction: Math.min(1, Math.max(0, (scrollTop - top) / height)),
      };
    }
  }
  const last = pages[pages.length - 1];
  return { page: Number(last.dataset.pageNumber) || pages.length, fraction: 0 };
}

function restoreScrollAnchor(container: HTMLElement | null, anchor: ScrollAnchor | null) {
  if (!container || !anchor) return;
  const target = container.querySelector<HTMLElement>(`[data-page-number="${anchor.page}"]`);
  if (!target) return;
  container.scrollTop = target.offsetTop + anchor.fraction * target.offsetHeight;
}

function scrollToPage(container: HTMLElement | null, page: number, behavior: ScrollBehavior = 'smooth') {
  if (!container) return;
  const target = container.querySelector<HTMLElement>(`[data-page-number="${page}"]`);
  if (target) container.scrollTo({ top: target.offsetTop, behavior });
}

/** Small inset so the highlight start isn't flush against the toolbar edge. */
const HIGHLIGHT_SCROLL_PAD_PX = 12;

function earliestHighlightTop(
  page: number,
  regions: RegionResult[],
  figures: FigureResult[],
): { y0: number; pageHeight: number } | null {
  let best: { y0: number; pageHeight: number } | null = null;
  for (const item of [...regions, ...figures]) {
    if (Number(item.page_number) !== page || item.bbox?.length !== 4 || !item.page_height) continue;
    const y0 = item.bbox[1];
    if (best == null || y0 < best.y0) best = { y0, pageHeight: item.page_height };
  }
  return best;
}

function scrollToHighlight(
  container: HTMLElement | null,
  page: number,
  regions: RegionResult[],
  figures: FigureResult[],
  behavior: ScrollBehavior = 'smooth',
) {
  if (!container) return;
  const shell = container.querySelector<HTMLElement>(`[data-page-number="${page}"]`);
  if (!shell) return;

  const containerRect = container.getBoundingClientRect();
  const surface = shell.querySelector<HTMLElement>('.pdfPageSurface');
  const earliest = earliestHighlightTop(page, regions, figures);
  if (surface && earliest && surface.offsetHeight > 0) {
    const surfaceRect = surface.getBoundingClientRect();
    const top = container.scrollTop
      + (surfaceRect.top - containerRect.top)
      + (earliest.y0 / earliest.pageHeight) * surface.offsetHeight
      - HIGHLIGHT_SCROLL_PAD_PX;
    container.scrollTo({ top: Math.max(0, top), behavior });
    return;
  }

  const painted = shell.querySelector<HTMLElement>('.pdfHighlightBox');
  if (painted) {
    const boxRect = painted.getBoundingClientRect();
    const top = container.scrollTop + (boxRect.top - containerRect.top) - HIGHLIGHT_SCROLL_PAD_PX;
    container.scrollTo({ top: Math.max(0, top), behavior });
    return;
  }

  container.scrollTo({ top: shell.offsetTop, behavior });
}

function pageFromScroll(container: HTMLElement): number {
  const pages = container.querySelectorAll<HTMLElement>('[data-page-number]');
  if (!pages.length) return 1;
  const probe = container.scrollTop + Math.min(48, container.clientHeight * 0.12);
  for (const page of pages) {
    if (page.offsetTop + page.offsetHeight > probe) {
      return Number(page.dataset.pageNumber) || 1;
    }
  }
  return Number(pages[pages.length - 1].dataset.pageNumber) || pages.length;
}

function fitScaleFor(mode: 'fit-width' | 'fit-page', pageSize: PageSize, container: HTMLElement): number {
  const availW = Math.max(80, container.clientWidth - PDF_CANVAS_PAD_X);
  const availH = Math.max(80, container.clientHeight - PDF_CANVAS_PAD_Y);
  if (mode === 'fit-width') return clampPdfFitZoom(availW / pageSize.width);
  return clampPdfFitZoom(Math.min(availW / pageSize.width, availH / pageSize.height));
}

function PdfSourceViewerImpl({
  source,
  highlightRegions = EMPTY_REGIONS,
  highlightFigures = [],
  compact = false,
  targetPage,
  jumpVersion = 0,
}: {
  source: SourceDocumentResult;
  highlightRegions?: RegionResult[];
  highlightFigures?: FigureResult[];
  compact?: boolean;
  targetPage?: number | null;
  jumpVersion?: number;
}) {
  const pagesRef = useRef<HTMLDivElement | null>(null);
  const pdfRef = useRef<pdfjsLib.PDFDocumentProxy | null>(null);
  const renderedSourceRef = useRef('');
  const scrollAnchorRef = useRef<ScrollAnchor | null>(null);
  const pageInputFocusedRef = useRef(false);
  const suppressPageTrackingRef = useRef(false);
  const citationJumpPendingRef = useRef(false);
  const scaleRef = useRef(PDF_ZOOM_DEFAULT);
  const zoomModeRef = useRef<ZoomMode>('fit-width');
  const [scale, setScale] = useState(PDF_ZOOM_DEFAULT);
  // Side-pane default: fill the available width so pages aren't cropped.
  const [zoomMode, setZoomMode] = useState<ZoomMode>('fit-width');
  const [error, setError] = useState<string | null>(null);
  const [pageCount, setPageCount] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageInput, setPageInput] = useState('1');
  const [pageSize, setPageSize] = useState<PageSize | null>(null);
  const [rendering, setRendering] = useState(false);
  const [showHighlights, setShowHighlights] = useState(() => {
    try { return localStorage.getItem('vera.showHighlights') !== '0'; } catch { return true; }
  });
  const highlightKey = useMemo(
    () => JSON.stringify([highlightRegions, highlightFigures]),
    [highlightRegions, highlightFigures],
  );
  const hasPassageHighlights = highlightRegions.some((region) => region.bbox?.length === 4);
  const hasFigureHighlights = highlightFigures.some((figure) => figure.bbox?.length === 4);

  scaleRef.current = scale;

  const rememberAnchor = useCallback(() => {
    // A resize can fire again while the scale render is rebuilding page shells.
    // Keep the anchor captured from the stable, pre-resize layout instead of
    // replacing it with a page inferred from the half-rebuilt document.
    if (citationJumpPendingRef.current || scrollAnchorRef.current) return;
    scrollAnchorRef.current = captureScrollAnchor(pagesRef.current);
  }, []);

  const commitZoomMode = useCallback((mode: ZoomMode) => {
    zoomModeRef.current = mode;
    setZoomMode(mode);
  }, []);

  const setManualScale = useCallback((updater: number | ((value: number) => number), snap = true) => {
    rememberAnchor();
    commitZoomMode('manual');
    setScale((value) => {
      const next = typeof updater === 'function' ? updater(value) : updater;
      return clampPdfZoom(next, snap);
    });
  }, [commitZoomMode, rememberAnchor]);

  const applyFitScale = useCallback((mode: 'fit-width' | 'fit-page') => {
    const container = pagesRef.current;
    if (!container || !pageSize) {
      commitZoomMode(mode);
      return;
    }
    rememberAnchor();
    commitZoomMode(mode);
    setScale(fitScaleFor(mode, pageSize, container));
  }, [commitZoomMode, pageSize, rememberAnchor]);

  const goToPage = (page: number, behavior: ScrollBehavior = 'smooth') => {
    if (!pageCount) return;
    const clamped = Math.min(pageCount, Math.max(1, Math.round(page)));
    suppressPageTrackingRef.current = true;
    setCurrentPage(clamped);
    setPageInput(String(clamped));
    scrollToPage(pagesRef.current, clamped, behavior);
    window.setTimeout(() => {
      suppressPageTrackingRef.current = false;
    }, behavior === 'smooth' ? 400 : 50);
  };

  const highlightRegionsRef = useRef(highlightRegions);
  const highlightFiguresRef = useRef(highlightFigures);
  const targetPageRef = useRef(targetPage);
  highlightRegionsRef.current = highlightRegions;
  highlightFiguresRef.current = highlightFigures;
  targetPageRef.current = targetPage;

  const goToHighlight = useCallback((page: number, behavior: ScrollBehavior = 'smooth') => {
    if (!pagesRef.current) return;
    const clamped = Math.max(1, Math.round(page));
    suppressPageTrackingRef.current = true;
    setCurrentPage(clamped);
    setPageInput(String(clamped));
    scrollToHighlight(
      pagesRef.current,
      clamped,
      highlightRegionsRef.current,
      highlightFiguresRef.current,
      behavior,
    );
    window.setTimeout(() => {
      suppressPageTrackingRef.current = false;
    }, behavior === 'smooth' ? 400 : 50);
  }, []);

  // Keep the page field in sync unless the user is editing it.
  useEffect(() => {
    if (!pageInputFocusedRef.current) setPageInput(String(currentPage));
  }, [currentPage]);

  // Keep the page fitted to the pane. Observe the container's border box so
  // scrollbar changes cannot masquerade as a pane resize. Manual zoom is
  // temporary: a real resize returns to fit-width; fit-page stays fit-page.
  useEffect(() => {
    if (!pageSize) return;
    const container = pagesRef.current;
    if (!container) return;

    const applyFit = (mode: 'fit-width' | 'fit-page') => {
      const next = fitScaleFor(mode, pageSize, container);
      commitZoomMode(mode);
      if (Math.abs(next - scaleRef.current) <= 0.005) return;
      rememberAnchor();
      setScale(next);
    };

    if (zoomModeRef.current !== 'manual') {
      applyFit(zoomModeRef.current === 'fit-page' ? 'fit-page' : 'fit-width');
    }

    const initialBox = container.getBoundingClientRect();
    let lastW = initialBox.width;
    let lastH = initialBox.height;
    const onResize = (entries: ResizeObserverEntry[]) => {
      const entry = entries[0];
      if (!entry) return;
      const borderBox = entry.borderBoxSize[0];
      const width = borderBox?.inlineSize ?? entry.contentRect.width;
      const height = borderBox?.blockSize ?? entry.contentRect.height;
      if (Math.abs(width - lastW) < 0.5 && Math.abs(height - lastH) < 0.5) return;
      lastW = width;
      lastH = height;
      applyFit(zoomModeRef.current === 'fit-page' ? 'fit-page' : 'fit-width');
    };

    const observer = new ResizeObserver(onResize);
    observer.observe(container);
    return () => observer.disconnect();
  }, [commitZoomMode, pageSize, rememberAnchor, source.url]);

  // Track the page nearest the top of the viewport while scrolling.
  useEffect(() => {
    const container = pagesRef.current;
    if (!container || !pageCount) return;
    let rafId: number | null = null;
    const onScroll = () => {
      if (suppressPageTrackingRef.current) return;
      if (rafId != null) return;
      rafId = requestAnimationFrame(() => {
        rafId = null;
        setCurrentPage(pageFromScroll(container));
      });
    };
    container.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
    return () => {
      container.removeEventListener('scroll', onScroll);
      if (rafId != null) cancelAnimationFrame(rafId);
    };
  }, [pageCount, scale, source.url]);

  // Ctrl/Cmd + mouse wheel (and trackpad pinch, which Chromium reports as a wheel
  // event with ctrlKey set) zooms in the same discrete steps as the toolbar buttons.
  useEffect(() => {
    const container = pagesRef.current;
    if (!container) return;
    let rafId: number | null = null;
    let accumulated = 0;
    let pendingSteps = 0;

    const onWheel = (event: WheelEvent) => {
      if (!event.ctrlKey && !event.metaKey) return;
      event.preventDefault();
      const distance = event.deltaMode === 1
        ? event.deltaY * 16
        : event.deltaMode === 2
          ? event.deltaY * PDF_ZOOM_WHEEL_THRESHOLD
          : event.deltaY;
      accumulated += distance;
      while (Math.abs(accumulated) >= PDF_ZOOM_WHEEL_THRESHOLD) {
        pendingSteps += accumulated > 0 ? -1 : 1;
        accumulated -= Math.sign(accumulated) * PDF_ZOOM_WHEEL_THRESHOLD;
      }
      if (pendingSteps !== 0 && rafId == null) {
        rafId = requestAnimationFrame(() => {
          rafId = null;
          const steps = pendingSteps;
          pendingSteps = 0;
          if (!steps) return;
          setManualScale((value) => value + steps * PDF_ZOOM_STEP);
        });
      }
    };

    container.addEventListener('wheel', onWheel, { passive: false });
    return () => {
      container.removeEventListener('wheel', onWheel);
      if (rafId != null) cancelAnimationFrame(rafId);
    };
  }, [setManualScale]);

  const onViewerKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.ctrlKey || event.metaKey) {
      if (event.key === '=' || event.key === '+') {
        event.preventDefault();
        setManualScale((value) => value + PDF_ZOOM_STEP);
      } else if (event.key === '-') {
        event.preventDefault();
        setManualScale((value) => value - PDF_ZOOM_STEP);
      } else if (event.key === '0') {
        event.preventDefault();
        setManualScale(PDF_ZOOM_DEFAULT);
      }
      return;
    }

    if (event.key === 'PageDown' || (event.key === 'ArrowDown' && event.altKey)) {
      event.preventDefault();
      goToPage(currentPage + 1);
    } else if (event.key === 'PageUp' || (event.key === 'ArrowUp' && event.altKey)) {
      event.preventDefault();
      goToPage(currentPage - 1);
    } else if (event.key === 'Home') {
      event.preventDefault();
      goToPage(1);
    } else if (event.key === 'End') {
      event.preventDefault();
      goToPage(pageCount);
    }
  };

  const commitPageInput = () => {
    const parsed = Number.parseInt(pageInput, 10);
    if (!Number.isFinite(parsed)) {
      setPageInput(String(currentPage));
      return;
    }
    goToPage(parsed);
  };

  const paintHighlights = useCallback((surface: HTMLElement, pageNum: number) => {
    let layer = surface.querySelector<HTMLElement>('.pdfHighlightLayer');
    if (!layer) {
      layer = document.createElement('div');
      layer.className = 'pdfHighlightLayer';
      const canvas = surface.querySelector('canvas');
      if (canvas) canvas.after(layer);
      else surface.append(layer);
    }
    layer.replaceChildren();
    for (const region of highlightRegions.filter((r) => Number(r.page_number) === pageNum && r.bbox?.length === 4)) {
      const box = document.createElement('div');
      box.className = 'pdfHighlightBox';
      Object.assign(box.style, regionStyle(region));
      layer.append(box);
    }
    for (const figure of highlightFigures.filter((item) => Number(item.page_number) === pageNum && item.bbox?.length === 4)) {
      const box = document.createElement('div');
      box.className = 'pdfHighlightBox pdfHighlightBox--figure';
      Object.assign(box.style, regionStyle(figure));
      layer.append(box);
    }
  }, [highlightFigures, highlightRegions]);

  const paintHighlightsRef = useRef(paintHighlights);
  paintHighlightsRef.current = paintHighlights;

  // Citation changes only need the overlay boxes updated — do not rebuild pages.
  // Jump directly to the highlight. Smooth-scrolling across a long document can
  // render intermediate virtualized pages and make citation navigation feel slow.
  useEffect(() => {
    const container = pagesRef.current;
    if (!container) return;
    for (const shell of container.querySelectorAll<HTMLElement>('[data-page-number]')) {
      if (!shell.dataset.rendered) continue;
      const pageNum = Number(shell.dataset.pageNumber);
      const surface = shell.querySelector<HTMLElement>('.pdfPageSurface');
      if (!pageNum || !surface) continue;
      paintHighlights(surface, pageNum);
    }
    if (!targetPage) return undefined;
    let canceled = false;
    const fitAndJump = async () => {
      const pdf = pdfRef.current;
      const container = pagesRef.current;
      if (
        zoomModeRef.current === 'fit-width'
        && pdf
        && container
        && renderedSourceRef.current === source.url
      ) {
        const pageNum = Math.min(pdf.numPages, Math.max(1, Math.round(targetPage)));
        const page = await pdf.getPage(pageNum);
        if (canceled || pdf !== pdfRef.current) return;
        const viewport = page.getViewport({ scale: 1 });
        const targetSize = { width: viewport.width, height: viewport.height };
        setPageSize(targetSize);
        const nextScale = fitScaleFor('fit-width', targetSize, container);
        if (Math.abs(nextScale - scaleRef.current) > 0.005) {
          citationJumpPendingRef.current = true;
          scrollAnchorRef.current = null;
          setScale(nextScale);
          return;
        }
      }
      goToHighlight(targetPage, 'auto');
    };
    void fitAndJump().catch((err: unknown) => {
      if (!canceled) setError(err instanceof Error ? err.message : 'Unable to fit cited PDF page');
    });
    return () => {
      canceled = true;
    };
  }, [goToHighlight, highlightKey, jumpVersion, pageCount, paintHighlights, source.url, targetPage]);

  // Main render effect: load PDF + set up virtualized rendering.
  // targetPage / highlights deliberately excluded — scroll + overlay effects handle those.
  useEffect(() => {
    let canceled = false;
    let observer: IntersectionObserver | null = null;
    const renderTasks = new Set<{ cancel: () => void }>();
    const sourceChanged = renderedSourceRef.current !== source.url;
    const container = pagesRef.current;
    const citationJumpPending = citationJumpPendingRef.current;
    const anchor = sourceChanged || citationJumpPending
      ? null
      : (scrollAnchorRef.current ?? captureScrollAnchor(container));

    // Drop stale shells immediately so a cancelled prior load cannot leave pages
    // marked rendered without canvases/highlights.
    container?.replaceChildren();

    async function load() {
      setError(null);
      setRendering(true);
      try {
        // Re-use cached PDFDocument across scale changes for the same file.
        if (!pdfRef.current || sourceChanged) {
          if (pdfRef.current) {
            void pdfRef.current.loadingTask.destroy();
            pdfRef.current = null;
          }
          const loadingTask = pdfjsLib.getDocument({
            url: source.url,
            useWorkerFetch: false,
          });
          const loadedPdf = await loadingTask.promise;
          if (canceled) {
            void loadingTask.destroy();
            return;
          }
          pdfRef.current = loadedPdf;
          renderedSourceRef.current = source.url;
        }
        const pdf = pdfRef.current;
        if (!pdf || canceled) return;
        if (!container || container !== pagesRef.current) return;

        setPageCount(pdf.numPages);

        const firstPage = await pdf.getPage(1);
        if (canceled) return;
        const baseViewport = firstPage.getViewport({ scale: 1 });
        setPageSize((prev) => (
          prev
          && Math.abs(prev.width - baseViewport.width) < 0.5
          && Math.abs(prev.height - baseViewport.height) < 0.5
            ? prev
            : { width: baseViewport.width, height: baseViewport.height }
        ));
        const defaultViewport = firstPage.getViewport({ scale });
        const defaultW = Math.floor(defaultViewport.width);
        const defaultH = Math.floor(defaultViewport.height);

        container.replaceChildren();

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
          if (i % 40 === 0) {
            await new Promise<void>((resolve) => {
              requestAnimationFrame(() => resolve());
            });
            if (canceled) return;
          }
        }

        const outputScale = window.devicePixelRatio || 1;

        const renderPage = async (pageNum: number) => {
          const shell = shells[pageNum - 1];
          if (!shell || shell.dataset.rendered || shell.dataset.rendering || canceled) return;
          shell.dataset.rendering = '1';

          try {
            const page = await pdf.getPage(pageNum);
            if (canceled) return;
            const viewport = page.getViewport({ scale });
            const cssW = Math.floor(viewport.width);
            const cssH = Math.floor(viewport.height);

            const surface = shell.querySelector<HTMLElement>('.pdfPageSurface')!;
            surface.style.width = `${cssW}px`;
            surface.style.height = `${cssH}px`;

            const canvas = document.createElement('canvas');
            canvas.width = Math.floor(cssW * outputScale);
            canvas.height = Math.floor(cssH * outputScale);
            canvas.style.width = `${cssW}px`;
            canvas.style.height = `${cssH}px`;
            const ctx = canvas.getContext('2d')!;
            if (outputScale !== 1) {
              ctx.setTransform(outputScale, 0, 0, outputScale, 0, 0);
            }

            const textLayerContainer = document.createElement('div');
            textLayerContainer.className = 'textLayer';

            surface.replaceChildren(canvas, textLayerContainer);
            paintHighlightsRef.current(surface, pageNum);

            const renderTask = page.render({ canvas, canvasContext: ctx, viewport });
            renderTasks.add(renderTask);
            try {
              await renderTask.promise;
            } catch (err) {
              if (canceled || (err instanceof Error && err.name === 'RenderingCancelledException')) return;
              throw err;
            } finally {
              renderTasks.delete(renderTask);
            }
            if (canceled) return;
            await new pdfjsLib.TextLayer({
              textContentSource: page.streamTextContent(),
              container: textLayerContainer,
              viewport,
            }).render();
            if (canceled) return;
            // Highlights may have arrived while this page was painting.
            paintHighlightsRef.current(surface, pageNum);
            shell.dataset.rendered = '1';
            shell.classList.remove('pdfPage--pending');
            // Citation jump may have landed before this page had layout; align now.
            if (!anchor && targetPageRef.current === pageNum) {
              scrollToHighlight(
                container,
                pageNum,
                highlightRegionsRef.current,
                highlightFiguresRef.current,
                'auto',
              );
            }
          } finally {
            delete shell.dataset.rendering;
          }
        };

        const priority = anchor?.page ?? targetPage ?? 1;
        await renderPage(priority);
        if (canceled) return;

        if (anchor) {
          restoreScrollAnchor(container, anchor);
          scrollAnchorRef.current = null;
          setCurrentPage(anchor.page);
        } else {
          const jump = targetPage ?? 1;
          scrollToHighlight(
            container,
            jump,
            highlightRegionsRef.current,
            highlightFiguresRef.current,
            'auto',
          );
          setCurrentPage(jump);
          scrollAnchorRef.current = null;
          citationJumpPendingRef.current = false;
        }

        observer = new IntersectionObserver(
          (entries) => {
            for (const entry of entries) {
              if (!entry.isIntersecting) continue;
              const el = entry.target as HTMLElement;
              const num = Number(el.dataset.pageNumber);
              if (num && !el.dataset.rendered && !el.dataset.rendering) {
                void renderPage(num).catch((err: unknown) => {
                  if (!canceled) setError(err instanceof Error ? err.message : 'Unable to render PDF page');
                });
              }
            }
          },
          { root: container, rootMargin: '300px 0px' },
        );
        for (const shell of shells) observer.observe(shell);
      } catch (err) {
        if (!canceled) setError(err instanceof Error ? err.message : 'Unable to render PDF');
      } finally {
        if (!canceled) {
          citationJumpPendingRef.current = false;
          setRendering(false);
        }
      }
    }

    void load();
    return () => {
      canceled = true;
      observer?.disconnect();
      for (const task of renderTasks) task.cancel();
      renderTasks.clear();
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scale, source.url]); // targetPage / highlightKey intentionally excluded

  // Release the PDF.js document when the viewer unmounts or the source changes.
  useEffect(() => () => {
    if (pdfRef.current) {
      void pdfRef.current.loadingTask.destroy();
      pdfRef.current = null;
      renderedSourceRef.current = '';
    }
  }, [source.url]);

  // Reset page UI when switching documents.
  useEffect(() => {
    setPageCount(0);
    setCurrentPage(1);
    setPageInput('1');
    commitZoomMode('fit-width');
    setScale(PDF_ZOOM_DEFAULT);
    scrollAnchorRef.current = null;
  }, [commitZoomMode, source.url]);

  return (
    <div className={`${compact ? 'pdfViewer compact' : 'pdfViewer'}${showHighlights ? '' : ' pdfViewer--hideHighlights'}`}>
      <div className="viewerToolbarWrap">
      <div className="viewerToolbar" role="toolbar" aria-label="Document viewer controls">
        <div className="viewerToolbarGroup viewerToolbarNav">
          <button
            type="button"
            className="viewerToolButton"
            onClick={() => goToPage(currentPage - 1)}
            disabled={!pageCount || currentPage <= 1}
            title="Previous page (Page Up)"
            aria-label="Previous page"
          >
            <ChevronLeft size={15} />
          </button>
          <label className="viewerPageControl">
            <span className="srOnly">Page</span>
            <input
              className="viewerPageInput"
              type="text"
              inputMode="numeric"
              value={pageInput}
              onFocus={() => { pageInputFocusedRef.current = true; }}
              onBlur={() => {
                pageInputFocusedRef.current = false;
                commitPageInput();
              }}
              onChange={(event) => setPageInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  event.preventDefault();
                  (event.target as HTMLInputElement).blur();
                } else if (event.key === 'Escape') {
                  setPageInput(String(currentPage));
                  (event.target as HTMLInputElement).blur();
                }
              }}
              aria-label="Current page"
              disabled={!pageCount}
            />
            <span className="viewerPageTotal" aria-live="polite">
              / {pageCount || '—'}
            </span>
          </label>
          <button
            type="button"
            className="viewerToolButton"
            onClick={() => goToPage(currentPage + 1)}
            disabled={!pageCount || currentPage >= pageCount}
            title="Next page (Page Down)"
            aria-label="Next page"
          >
            <ChevronRight size={15} />
          </button>
        </div>

        <span className="viewerToolbarStatus" aria-live="polite">
          {rendering ? 'Rendering…' : null}
        </span>

        {(hasPassageHighlights || hasFigureHighlights) && showHighlights ? (
          <div className="viewerHighlightLegend" aria-hidden="true">
            {hasPassageHighlights ? <span className="viewerLegendSwatch viewerLegendSwatch--passage">Passage</span> : null}
            {hasFigureHighlights ? <span className="viewerLegendSwatch viewerLegendSwatch--figure">Figure</span> : null}
          </div>
        ) : null}

        <div className="viewerToolbarGroup">
          <button
            type="button"
            className={showHighlights ? 'viewerToolButton activeNow' : 'viewerToolButton'}
            onClick={() => setShowHighlights((value) => {
              const next = !value;
              try { localStorage.setItem('vera.showHighlights', next ? '1' : '0'); } catch { /* ignore persistence errors */ }
              return next;
            })}
            title={showHighlights ? 'Hide highlight regions' : 'Show highlight regions'}
            aria-label={showHighlights ? 'Hide highlight regions' : 'Show highlight regions'}
            aria-pressed={showHighlights}
          >
            <Highlighter size={14} />
            <span className="viewerToolLabel">Highlights</span>
          </button>
          <button
            type="button"
            className={zoomMode === 'fit-width' ? 'viewerToolButton activeNow' : 'viewerToolButton'}
            onClick={() => applyFitScale('fit-width')}
            title="Fit width"
            aria-label="Fit width"
            aria-pressed={zoomMode === 'fit-width'}
          >
            <Scan size={14} />
            <span className="viewerToolLabel">Width</span>
          </button>
          <button
            type="button"
            className={zoomMode === 'fit-page' ? 'viewerToolButton activeNow' : 'viewerToolButton'}
            onClick={() => applyFitScale('fit-page')}
            title="Fit page"
            aria-label="Fit page"
            aria-pressed={zoomMode === 'fit-page'}
          >
            <Maximize2 size={14} />
            <span className="viewerToolLabel">Page</span>
          </button>
          <button
            type="button"
            className="viewerToolButton"
            onClick={() => setManualScale((value) => value - PDF_ZOOM_STEP)}
            disabled={scale <= PDF_ZOOM_MIN}
            title="Zoom out (Ctrl+-)"
            aria-label="Zoom out"
          >
            <ZoomOut size={14} />
          </button>
          <button
            type="button"
            className="viewerToolButton viewerZoomLevel"
            onClick={() => setManualScale(PDF_ZOOM_DEFAULT)}
            title="Reset zoom to 100% (Ctrl+0)"
            aria-label={`Zoom level ${Math.round(scale * 100)} percent. Reset to 100 percent.`}
          >
            {Math.round(scale * 100)}%
          </button>
          <button
            type="button"
            className="viewerToolButton"
            onClick={() => setManualScale((value) => value + PDF_ZOOM_STEP)}
            disabled={scale >= PDF_ZOOM_MAX}
            title="Zoom in (Ctrl+=)"
            aria-label="Zoom in"
          >
            <ZoomIn size={14} />
          </button>
        </div>
      </div>
      </div>
      {error ? <div className="errorBanner" role="alert">{error}</div> : null}
      <div
        className="pdfCanvasWrap"
        ref={pagesRef}
        tabIndex={0}
        onKeyDown={onViewerKeyDown}
        aria-label="PDF pages"
      />
    </div>
  );
}

// Memoized so this doesn't re-render (and re-run its render body) when unrelated
// App state changes, e.g. every keystroke in the chat composer.
export const PdfSourceViewer = React.memo(PdfSourceViewerImpl);
