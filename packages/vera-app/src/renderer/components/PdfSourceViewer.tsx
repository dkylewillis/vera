import React, { type CSSProperties, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import * as pdfjsLib from 'pdfjs-dist';
import pdfWorkerUrl from 'pdfjs-dist/build/pdf.worker.mjs?url';
import {
  Download,
  Highlighter,
  Menu,
  Minus,
  Plus,
  Printer,
  RotateCcw,
} from 'lucide-react';
import type { FigureResult, RegionResult, SourceDocumentResult } from '../types';
import { EMPTY_REGIONS } from '../lib/constants';
import {
  fitScaleFor,
  fitPageCenterPadding,
  nextRotationCcw,
  pagePointToVisualFraction,
  pageSizeForNumber,
  pageWithMostVisibleArea,
  pdfFitViewport,
  PDF_CANVAS_EDGE_PAD,
  PDF_THUMB_WIDTH,
  scrollTopToCenterPage,
  thumbnailSizeFor,
  visualPageSize,
  type PdfPageSize,
  type PdfRotation,
} from '../lib/pdfZoom';

pdfjsLib.GlobalWorkerOptions.workerSrc = pdfWorkerUrl;

function FitWidthIcon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" aria-hidden="true" focusable="false">
      <rect
        x="1.25"
        y="4.25"
        width="13.5"
        height="7.5"
        rx="2.2"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
      />
    </svg>
  );
}

function FitPageIcon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" aria-hidden="true" focusable="false">
      <rect
        x="2.35"
        y="2.35"
        width="11.3"
        height="11.3"
        rx="2.4"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
      />
    </svg>
  );
}

function layoutRotatedSurface(
  wrapper: HTMLElement,
  surface: HTMLElement,
  cssW: number,
  cssH: number,
  rotation: number,
) {
  const visual = visualPageSize({ width: cssW, height: cssH }, rotation);
  wrapper.style.width = `${visual.width}px`;
  wrapper.style.height = `${visual.height}px`;
  surface.style.width = `${cssW}px`;
  surface.style.height = `${cssH}px`;
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

const PDF_ZOOM_MIN = 0.5;
const PDF_ZOOM_MAX = 2.5;
const PDF_ZOOM_DEFAULT = 1;
const PDF_ZOOM_STEP = 0.25;
/** Wheel/trackpad delta accumulated before applying one discrete zoom step. */
const PDF_ZOOM_WHEEL_THRESHOLD = 80;
type ZoomMode = 'manual' | 'fit-width' | 'fit-page';

type ScrollAnchor = {
  page: number;
  fraction: number;
};

function clampPdfZoom(value: number, snap = true): number {
  const clamped = Math.min(PDF_ZOOM_MAX, Math.max(PDF_ZOOM_MIN, value));
  if (!snap) return clamped;
  const steps = Math.round((clamped - PDF_ZOOM_MIN) / PDF_ZOOM_STEP);
  return Math.min(PDF_ZOOM_MAX, Math.max(PDF_ZOOM_MIN, PDF_ZOOM_MIN + steps * PDF_ZOOM_STEP));
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

function centerPageInViewport(container: HTMLElement | null, page: number) {
  if (!container) return;
  const target = container.querySelector<HTMLElement>(`[data-page-number="${page}"]`);
  if (!target) {
    container.style.paddingTop = '';
    container.style.paddingBottom = '';
    return;
  }
  const pad = fitPageCenterPadding(
    container.clientHeight,
    target.offsetHeight,
    PDF_CANVAS_EDGE_PAD,
  );
  container.style.paddingTop = `${pad}px`;
  container.style.paddingBottom = `${pad}px`;
  const containerRect = container.getBoundingClientRect();
  const targetRect = target.getBoundingClientRect();
  container.scrollTop = scrollTopToCenterPage(
    container.scrollTop,
    targetRect.top - containerRect.top,
    target.offsetHeight,
    container.clientHeight,
  );
}

function clearFitPagePadding(container: HTMLElement | null) {
  if (!container) return;
  container.style.paddingTop = '';
  container.style.paddingBottom = '';
}

/** Small inset so the highlight start isn't flush against the toolbar edge. */
const HIGHLIGHT_SCROLL_PAD_PX = 12;

function earliestHighlight(
  page: number,
  regions: RegionResult[],
  figures: FigureResult[],
): { x0: number; y0: number; pageWidth: number; pageHeight: number } | null {
  let best: { x0: number; y0: number; pageWidth: number; pageHeight: number } | null = null;
  for (const item of [...regions, ...figures]) {
    if (Number(item.page_number) !== page || item.bbox?.length !== 4 || !item.page_width || !item.page_height) continue;
    const x0 = item.bbox[0];
    const y0 = item.bbox[1];
    if (best == null || y0 < best.y0 || (y0 === best.y0 && x0 < best.x0)) {
      best = { x0, y0, pageWidth: item.page_width, pageHeight: item.page_height };
    }
  }
  return best;
}

function scrollToHighlight(
  container: HTMLElement | null,
  page: number,
  regions: RegionResult[],
  figures: FigureResult[],
  behavior: ScrollBehavior = 'smooth',
  rotation: number = 0,
) {
  if (!container) return;
  const shell = container.querySelector<HTMLElement>(`[data-page-number="${page}"]`);
  if (!shell) return;

  const containerRect = container.getBoundingClientRect();
  const painted = shell.querySelector<HTMLElement>('.pdfHighlightBox');
  if (painted) {
    const boxRect = painted.getBoundingClientRect();
    const top = container.scrollTop + (boxRect.top - containerRect.top) - HIGHLIGHT_SCROLL_PAD_PX;
    container.scrollTo({ top: Math.max(0, top), behavior });
    return;
  }

  const wrapper = shell.querySelector<HTMLElement>('.pdfPageRotate') ?? shell;
  const earliest = earliestHighlight(page, regions, figures);
  if (earliest && wrapper.offsetHeight > 0) {
    const { fy } = pagePointToVisualFraction(
      earliest.x0,
      earliest.y0,
      earliest.pageWidth,
      earliest.pageHeight,
      rotation,
    );
    const wrapperRect = wrapper.getBoundingClientRect();
    const top = container.scrollTop
      + (wrapperRect.top - containerRect.top)
      + fy * wrapper.offsetHeight
      - HIGHLIGHT_SCROLL_PAD_PX;
    container.scrollTo({ top: Math.max(0, top), behavior });
    return;
  }

  container.scrollTo({ top: shell.offsetTop, behavior });
}

function pageFromScroll(container: HTMLElement): number {
  const pages = [...container.querySelectorAll<HTMLElement>('[data-page-number]')].map((el) => ({
    page: Number(el.dataset.pageNumber) || 1,
    top: el.offsetTop,
    height: el.offsetHeight,
  }));
  return pageWithMostVisibleArea(pages, {
    scrollTop: container.scrollTop,
    height: container.clientHeight,
  });
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
  const thumbsRef = useRef<HTMLDivElement | null>(null);
  const sourceBusyRef = useRef(false);
  const pdfRef = useRef<pdfjsLib.PDFDocumentProxy | null>(null);
  const pageSizesRef = useRef<PdfPageSize[]>([]);
  const renderedSourceRef = useRef('');
  const scrollAnchorRef = useRef<ScrollAnchor | null>(null);
  const pageInputFocusedRef = useRef(false);
  const suppressPageTrackingRef = useRef(false);
  const fitWidthPageRef = useRef(1);
  const scaleRef = useRef(PDF_ZOOM_DEFAULT);
  const zoomModeRef = useRef<ZoomMode>('fit-width');
  const [scale, setScale] = useState(PDF_ZOOM_DEFAULT);
  // Side-pane default: fill the available width so pages aren't cropped.
  const [zoomMode, setZoomMode] = useState<ZoomMode>('fit-width');
  const [error, setError] = useState<string | null>(null);
  const [pageCount, setPageCount] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageInput, setPageInput] = useState('1');
  const [pageSizes, setPageSizes] = useState<PdfPageSize[]>([]);
  const [rendering, setRendering] = useState(false);
  const [showHighlights, setShowHighlights] = useState(() => {
    try { return localStorage.getItem('vera.showHighlights') !== '0'; } catch { return true; }
  });
  const [showThumbnails, setShowThumbnails] = useState(() => {
    try { return localStorage.getItem('vera.pdfThumbnails') !== '0'; } catch { return true; }
  });
  const [sourceBusy, setSourceBusy] = useState<'download' | 'print' | null>(null);
  const [rotation, setRotation] = useState<PdfRotation>(0);
  const rotationRef = useRef<PdfRotation>(0);
  const highlightKey = useMemo(
    () => JSON.stringify([highlightRegions, highlightFigures]),
    [highlightRegions, highlightFigures],
  );
  const currentPageSize = pageSizeForNumber(pageSizes, currentPage);
  const visualCurrentPage = currentPageSize ? visualPageSize(currentPageSize, rotation) : null;
  const fitContainer = pagesRef.current;
  const currentPageFitScale = visualCurrentPage && fitContainer
    ? fitScaleFor('fit-width', [visualCurrentPage], pdfFitViewport(fitContainer))
    : null;
  const isCurrentPageFitWidth = zoomMode === 'fit-width'
    && currentPageFitScale !== null
    && Math.abs(scale - currentPageFitScale) <= 0.005;

  scaleRef.current = scale;
  rotationRef.current = rotation;

  const rememberAnchor = useCallback(() => {
    // A resize can fire again while the scale render is rebuilding page shells.
    // Keep the anchor captured from the stable, pre-resize layout instead of
    // replacing it with a page inferred from the half-rebuilt document.
    if (scrollAnchorRef.current) return;
    scrollAnchorRef.current = captureScrollAnchor(pagesRef.current);
  }, []);

  const commitZoomMode = useCallback((mode: ZoomMode) => {
    zoomModeRef.current = mode;
    setZoomMode(mode);
  }, []);

  const setManualScale = useCallback((updater: number | ((value: number) => number), snap = true) => {
    rememberAnchor();
    commitZoomMode('manual');
    clearFitPagePadding(pagesRef.current);
    setScale((value) => {
      const next = typeof updater === 'function' ? updater(value) : updater;
      return clampPdfZoom(next, snap);
    });
  }, [commitZoomMode, rememberAnchor]);

  const applyFitScale = useCallback((mode: 'fit-width' | 'fit-page') => {
    const container = pagesRef.current;
    if (!container || pageSizes.length === 0) {
      commitZoomMode(mode);
      return;
    }
    const pageNumber = pageFromScroll(container);
    const page = pageSizeForNumber(pageSizes, pageNumber);
    const fitSizes = page ? [visualPageSize(page, rotation)] : pageSizes;
    fitWidthPageRef.current = pageNumber;
    if (mode === 'fit-page') {
      scrollAnchorRef.current = null;
      setCurrentPage(pageNumber);
      setPageInput(String(pageNumber));
    } else {
      rememberAnchor();
      clearFitPagePadding(container);
    }
    commitZoomMode(mode);
    const next = fitScaleFor(mode, fitSizes, pdfFitViewport(container));
    if (mode === 'fit-page' && Math.abs(next - scaleRef.current) <= 0.005) {
      centerPageInViewport(container, pageNumber);
      return;
    }
    setScale(next);
  }, [commitZoomMode, pageSizes, rememberAnchor, rotation]);

  const goToPage = (page: number, behavior: ScrollBehavior = 'smooth') => {
    if (!pageCount) return;
    const clamped = Math.min(pageCount, Math.max(1, Math.round(page)));
    suppressPageTrackingRef.current = true;
    setCurrentPage(clamped);
    setPageInput(String(clamped));
    if (zoomModeRef.current === 'fit-page') {
      fitWidthPageRef.current = clamped;
      centerPageInViewport(pagesRef.current, clamped);
    } else {
      scrollToPage(pagesRef.current, clamped, behavior);
    }
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
    if (zoomModeRef.current === 'fit-page') {
      fitWidthPageRef.current = clamped;
      centerPageInViewport(pagesRef.current, clamped);
    } else {
      scrollToHighlight(
        pagesRef.current,
        clamped,
        highlightRegionsRef.current,
        highlightFiguresRef.current,
        behavior,
        rotationRef.current,
      );
    }
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
    if (pageSizes.length === 0) return;
    const container = pagesRef.current;
    if (!container) return;

    const applyFit = (mode: 'fit-width' | 'fit-page') => {
      const page = pageSizeForNumber(pageSizes, fitWidthPageRef.current);
      const fitSizes = page ? [visualPageSize(page, rotationRef.current)] : pageSizes;
      const next = fitScaleFor(mode, fitSizes, pdfFitViewport(container));
      commitZoomMode(mode);
      if (Math.abs(next - scaleRef.current) <= 0.005) {
        if (mode === 'fit-page') centerPageInViewport(container, fitWidthPageRef.current);
        else clearFitPagePadding(container);
        return;
      }
      if (mode === 'fit-page') {
        scrollAnchorRef.current = null;
      } else {
        rememberAnchor();
        clearFitPagePadding(container);
      }
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
    observer.observe(container, { box: 'border-box' });
    return () => observer.disconnect();
  }, [commitZoomMode, pageSizes, rememberAnchor, source.url, rotation]);

  // Track the page that occupies the most of the well while scrolling.
  useEffect(() => {
    const container = pagesRef.current;
    if (!container || !pageCount) return;
    let rafId: number | null = null;
    const trackingIsSuppressed = () => (
      suppressPageTrackingRef.current || scrollAnchorRef.current !== null
    );
    const onScroll = () => {
      // Fit/zoom renders temporarily rebuild every page at a new height. Keep
      // showing the captured page until that layout's scroll anchor is restored.
      if (trackingIsSuppressed()) return;
      if (rafId != null) return;
      rafId = requestAnimationFrame(() => {
        rafId = null;
        // A resize may have started after this frame was queued.
        if (trackingIsSuppressed()) return;
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
    goToHighlight(targetPage, 'auto');
    return undefined;
  }, [goToHighlight, highlightKey, jumpVersion, pageCount, paintHighlights, source.url, targetPage]);

  // Main render effect: load PDF + set up virtualized rendering.
  // targetPage / highlights deliberately excluded — scroll + overlay effects handle those.
  useEffect(() => {
    let canceled = false;
    let observer: IntersectionObserver | null = null;
    const renderTasks = new Set<{ cancel: () => void }>();
    const sourceChanged = renderedSourceRef.current !== source.url;
    const container = pagesRef.current;
    const shouldCenterFittedPage = zoomModeRef.current === 'fit-page';
    const fittedPage = fitWidthPageRef.current;
    const anchor = sourceChanged || shouldCenterFittedPage
      ? null
      : (scrollAnchorRef.current ?? captureScrollAnchor(container));

    // Clear immediately when changing documents. Scale-only renders keep the
    // existing page stack visible until its replacement is ready.
    if (sourceChanged) {
      container?.replaceChildren();
      pageSizesRef.current = [];
      setPageSizes([]);
    }

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

        let documentPageSizes = pageSizesRef.current;
        if (documentPageSizes.length !== pdf.numPages) {
          documentPageSizes = [];
          for (let i = 1; i <= pdf.numPages; i++) {
            const page = await pdf.getPage(i);
            if (canceled) return;
            const viewport = page.getViewport({ scale: 1 });
            documentPageSizes.push({ width: viewport.width, height: viewport.height });
            if (i % 40 === 0) {
              await new Promise<void>((resolve) => {
                requestAnimationFrame(() => resolve());
              });
              if (canceled) return;
            }
          }
          pageSizesRef.current = documentPageSizes;
          setPageSizes(documentPageSizes);
        }

        const shells: HTMLElement[] = [];
        const fragment = document.createDocumentFragment();
        for (let i = 1; i <= pdf.numPages; i++) {
          const pageSize = documentPageSizes[i - 1];
          const shell = document.createElement('article');
          shell.className = 'pdfPage pdfPage--pending';
          shell.dataset.pageNumber = String(i);
          const rotate = document.createElement('div');
          rotate.className = 'pdfPageRotate';
          const surface = document.createElement('div');
          surface.className = 'pdfPageSurface';
          const cssW = Math.floor(pageSize.width * scale);
          const cssH = Math.floor(pageSize.height * scale);
          layoutRotatedSurface(rotate, surface, cssW, cssH, rotationRef.current);
          rotate.append(surface);
          shell.append(rotate);
          fragment.append(shell);
          shells.push(shell);
          if (i % 40 === 0) {
            await new Promise<void>((resolve) => {
              requestAnimationFrame(() => resolve());
            });
            if (canceled) return;
          }
        }

        // Swap the complete layout in one operation and restore its position
        // before the browser can paint an intermediate scroll location.
        container.replaceChildren(fragment);
        if (shouldCenterFittedPage) centerPageInViewport(container, fittedPage);
        else if (anchor) restoreScrollAnchor(container, anchor);

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
            const wrapper = shell.querySelector<HTMLElement>('.pdfPageRotate');
            if (wrapper) layoutRotatedSurface(wrapper, surface, cssW, cssH, rotationRef.current);
            else {
              surface.style.width = `${cssW}px`;
              surface.style.height = `${cssH}px`;
            }

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
            // PDF.js positions text in page-relative percentages, but sizes the
            // invisible selectable glyphs with this viewport scale.
            textLayerContainer.style.setProperty('--total-scale-factor', String(scale));

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
            if (!anchor && zoomModeRef.current !== 'fit-page' && targetPageRef.current === pageNum) {
              scrollToHighlight(
                container,
                pageNum,
                highlightRegionsRef.current,
                highlightFiguresRef.current,
                'auto',
                rotationRef.current,
              );
            }
          } finally {
            delete shell.dataset.rendering;
          }
        };

        const priority = shouldCenterFittedPage
          ? fittedPage
          : (anchor?.page ?? targetPage ?? 1);
        await renderPage(priority);
        if (canceled) return;

        if (shouldCenterFittedPage) {
          centerPageInViewport(container, fittedPage);
          scrollAnchorRef.current = null;
          setCurrentPage(fittedPage);
        } else if (anchor) {
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
            rotationRef.current,
          );
          setCurrentPage(jump);
          scrollAnchorRef.current = null;
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

  // Low-res sidebar thumbs. Independent of main-page zoom so scale changes
  // do not rebuild the rail.
  useEffect(() => {
    const pdf = pdfRef.current;
    const list = thumbsRef.current;
    if (!showThumbnails || !pdf || !list || pageSizes.length !== pageCount || pageCount === 0) {
      return undefined;
    }

    let canceled = false;
    const renderTasks = new Set<{ cancel: () => void }>();
    const outputScale = Math.min(2, window.devicePixelRatio || 1);

    const renderThumb = async (pageNum: number) => {
      const button = list.querySelector<HTMLElement>(`[data-thumb-page="${pageNum}"]`);
      const surface = button?.querySelector<HTMLElement>('.pdfThumbnailSurface');
      if (!surface || surface.dataset.rendered || surface.dataset.rendering || canceled) return;
      const pageSize = pageSizes[pageNum - 1];
      if (!pageSize) return;
      surface.dataset.rendering = '1';
      try {
        const page = await pdf.getPage(pageNum);
        if (canceled) return;
        const thumb = thumbnailSizeFor(pageSize);
        const viewport = page.getViewport({ scale: thumb.width / pageSize.width });
        const canvas = document.createElement('canvas');
        canvas.width = Math.floor(thumb.width * outputScale);
        canvas.height = Math.floor(thumb.height * outputScale);
        canvas.style.width = `${thumb.width}px`;
        canvas.style.height = `${thumb.height}px`;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;
        if (outputScale !== 1) ctx.setTransform(outputScale, 0, 0, outputScale, 0, 0);
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
        surface.replaceChildren(canvas);
        surface.dataset.rendered = '1';
      } finally {
        delete surface.dataset.rendering;
      }
    };

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          const pageNum = Number((entry.target as HTMLElement).dataset.thumbPage);
          if (pageNum) {
            void renderThumb(pageNum).catch(() => {
              /* leave the empty surface; the main page still renders */
            });
          }
        }
      },
      { root: list, rootMargin: '160px 0px' },
    );
    for (const button of list.querySelectorAll<HTMLElement>('[data-thumb-page]')) {
      observer.observe(button);
    }

    return () => {
      canceled = true;
      observer.disconnect();
      for (const task of renderTasks) task.cancel();
      renderTasks.clear();
    };
  }, [pageCount, pageSizes, showThumbnails, source.url]);

  useEffect(() => {
    if (!showThumbnails) return;
    const current = thumbsRef.current?.querySelector<HTMLElement>(
      `[data-thumb-page="${currentPage}"]`,
    );
    current?.scrollIntoView({ block: 'nearest' });
  }, [currentPage, showThumbnails]);

  useEffect(() => {
    const container = pagesRef.current;
    if (!container || pageSizes.length === 0) return;
    rememberAnchor();
    for (const shell of container.querySelectorAll<HTMLElement>('[data-page-number]')) {
      const wrapper = shell.querySelector<HTMLElement>('.pdfPageRotate');
      const surface = shell.querySelector<HTMLElement>('.pdfPageSurface');
      const pageSize = pageSizes[Number(shell.dataset.pageNumber) - 1];
      if (!wrapper || !surface || !pageSize) continue;
      layoutRotatedSurface(
        wrapper,
        surface,
        Math.floor(pageSize.width * scaleRef.current),
        Math.floor(pageSize.height * scaleRef.current),
        rotation,
      );
    }
    if (zoomModeRef.current === 'fit-page') {
      centerPageInViewport(container, fitWidthPageRef.current);
    }
  }, [pageSizes, rememberAnchor, rotation]);

  // Reset page UI when switching documents.
  useEffect(() => {
    setPageCount(0);
    setPageSizes([]);
    setCurrentPage(1);
    setPageInput('1');
    fitWidthPageRef.current = targetPageRef.current
      ? Math.max(1, Math.round(targetPageRef.current))
      : 1;
    commitZoomMode('fit-width');
    setScale(PDF_ZOOM_DEFAULT);
    setRotation(0);
    rotationRef.current = 0;
    scrollAnchorRef.current = null;
    clearFitPagePadding(pagesRef.current);
  }, [commitZoomMode, source.url]);

  const fetchSourceBlob = useCallback(async () => {
    const response = await fetch(source.url);
    if (!response.ok) throw new Error('Unable to read the source PDF');
    return response.blob();
  }, [source.url]);

  const downloadSource = useCallback(async () => {
    if (sourceBusyRef.current) return;
    sourceBusyRef.current = true;
    setSourceBusy('download');
    try {
      const blob = await fetchSourceBlob();
      const href = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = href;
      link.download = source.filename || 'document.pdf';
      link.rel = 'noopener';
      document.body.append(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(href), 2_000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to download PDF');
    } finally {
      sourceBusyRef.current = false;
      setSourceBusy(null);
    }
  }, [fetchSourceBlob, source.filename]);

  const printSource = useCallback(async () => {
    if (sourceBusyRef.current) return;
    sourceBusyRef.current = true;
    setSourceBusy('print');
    try {
      const blob = await fetchSourceBlob();
      const href = URL.createObjectURL(blob);
      const frame = document.createElement('iframe');
      frame.className = 'pdfPrintFrame';
      frame.src = href;
      const cleanup = () => {
        frame.remove();
        URL.revokeObjectURL(href);
      };
      frame.addEventListener('load', () => {
        try {
          frame.contentWindow?.focus();
          frame.contentWindow?.print();
        } finally {
          window.setTimeout(cleanup, 60_000);
        }
      }, { once: true });
      document.body.append(frame);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to print PDF');
    } finally {
      sourceBusyRef.current = false;
      setSourceBusy(null);
    }
  }, [fetchSourceBlob]);

  const viewerClass = [
    compact ? 'pdfViewer compact' : 'pdfViewer',
    showHighlights ? '' : 'pdfViewer--hideHighlights',
    showThumbnails ? 'pdfViewer--thumbs' : '',
  ].filter(Boolean).join(' ');

  return (
    <div
      className={viewerClass}
      style={{ ['--pdf-rotation' as string]: `${rotation}deg` }}
    >
      <div className="viewerToolbarWrap">
      <div className="viewerToolbar" role="toolbar" aria-label="Document viewer controls">
        <div className="viewerToolbarGroup">
          <button
            type="button"
            className={showThumbnails ? 'viewerToolButton activeNow' : 'viewerToolButton'}
            onClick={() => setShowThumbnails((value) => {
              const next = !value;
              try { localStorage.setItem('vera.pdfThumbnails', next ? '1' : '0'); } catch { /* ignore persistence errors */ }
              return next;
            })}
            title={showThumbnails ? 'Hide page thumbnails' : 'Show page thumbnails'}
            aria-label={showThumbnails ? 'Hide page thumbnails' : 'Show page thumbnails'}
            aria-pressed={showThumbnails}
          >
            <Menu size={16} />
          </button>
        </div>

        <div className="viewerToolbarGroup viewerToolbarNav">
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
        </div>

        <span className="viewerToolbarDivider" aria-hidden="true" />

        <div className="viewerToolbarGroup viewerToolbarZoom">
          <button
            type="button"
            className="viewerToolButton"
            onClick={() => setManualScale((value) => value - PDF_ZOOM_STEP)}
            disabled={scale <= PDF_ZOOM_MIN}
            title="Zoom out (Ctrl+-)"
            aria-label="Zoom out"
          >
            <Minus size={16} />
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
            <Plus size={16} />
          </button>
        </div>

        <span className="viewerToolbarDivider" aria-hidden="true" />

        <div className="viewerToolbarGroup">
          <button
            type="button"
            className={isCurrentPageFitWidth ? 'viewerToolButton activeNow' : 'viewerToolButton'}
            onClick={() => applyFitScale('fit-width')}
            title="Fit width"
            aria-label="Fit width"
            aria-pressed={isCurrentPageFitWidth}
          >
            <FitWidthIcon size={16} />
          </button>
          <button
            type="button"
            className={zoomMode === 'fit-page' ? 'viewerToolButton activeNow' : 'viewerToolButton'}
            onClick={() => applyFitScale('fit-page')}
            title="Fit page"
            aria-label="Fit page"
            aria-pressed={zoomMode === 'fit-page'}
          >
            <FitPageIcon size={16} />
          </button>
          <button
            type="button"
            className="viewerToolButton"
            onClick={() => {
              rememberAnchor();
              setRotation((value) => nextRotationCcw(value));
            }}
            title="Rotate counterclockwise"
            aria-label="Rotate counterclockwise"
          >
            <RotateCcw size={16} />
          </button>
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
            <Highlighter size={16} />
          </button>
        </div>

        <span className="viewerToolbarStatus" aria-live="polite">
          {rendering ? 'Rendering…' : null}
        </span>

        <div className="viewerToolbarGroup viewerToolbarEnd">
          <button
            type="button"
            className="viewerToolButton"
            onClick={() => void downloadSource()}
            disabled={Boolean(sourceBusy)}
            title="Download"
            aria-label="Download PDF"
          >
            <Download size={16} />
          </button>
          <button
            type="button"
            className="viewerToolButton"
            onClick={() => void printSource()}
            disabled={Boolean(sourceBusy)}
            title="Print"
            aria-label="Print PDF"
          >
            <Printer size={16} />
          </button>
        </div>
      </div>
      </div>
      {error ? <div className="errorBanner" role="alert">{error}</div> : null}
      <div className="pdfViewerBody">
        {showThumbnails ? (
          <aside className="pdfThumbnailSidebar" aria-label="Page thumbnails">
            <div className="pdfThumbnailList" ref={thumbsRef}>
              {Array.from({ length: pageCount }, (_, index) => {
                const page = index + 1;
                const size = pageSizes[index];
                const unrotated = size
                  ? thumbnailSizeFor(size)
                  : { width: PDF_THUMB_WIDTH, height: Math.round(PDF_THUMB_WIDTH * 11 / 8.5) };
                const layout = visualPageSize(unrotated, rotation);
                return (
                  <button
                    key={page}
                    type="button"
                    className={page === currentPage ? 'pdfThumbnail is-current' : 'pdfThumbnail'}
                    data-thumb-page={page}
                    onClick={() => goToPage(page)}
                    title={`Page ${page}`}
                    aria-label={`Page ${page}`}
                    aria-current={page === currentPage ? 'page' : undefined}
                  >
                    <span
                      className="pdfThumbnailRotate"
                      style={{ width: layout.width, height: layout.height }}
                    >
                      <span
                        className="pdfThumbnailSurface"
                        style={{ width: unrotated.width, height: unrotated.height }}
                      />
                    </span>
                    <span className="pdfThumbnailLabel">{page}</span>
                  </button>
                );
              })}
            </div>
          </aside>
        ) : null}
        <div
          className={zoomMode === 'fit-page' ? 'pdfCanvasWrap pdfCanvasWrap--fitPage' : 'pdfCanvasWrap'}
          ref={pagesRef}
          tabIndex={0}
          onKeyDown={onViewerKeyDown}
          aria-label="PDF pages"
        />
      </div>
    </div>
  );
}

// Memoized so this doesn't re-render (and re-run its render body) when unrelated
// App state changes, e.g. every keystroke in the chat composer.
export const PdfSourceViewer = React.memo(PdfSourceViewerImpl);
