export type PdfPageSize = {
  width: number;
  height: number;
};

export type PdfFitMode = 'fit-width' | 'fit-page';
export type PdfRotation = 0 | 90 | 180 | 270;

const PDF_ZOOM_MAX = 2.5;
/** Padding inside `.pdfCanvasWrap` (16px on each edge). */
export const PDF_CANVAS_EDGE_PAD = 16;
const PDF_CANVAS_PAD_X = PDF_CANVAS_EDGE_PAD * 2;
const PDF_CANVAS_PAD_Y = PDF_CANVAS_EDGE_PAD * 2;
/** CSS width of a thumbnail page surface (matches `.pdfThumbnailSurface`). */
export const PDF_THUMB_WIDTH = 88;

function clampPdfFitZoom(value: number): number {
  return Math.min(PDF_ZOOM_MAX, Math.max(Number.EPSILON, value));
}

export function pageSizeForNumber(
  pageSizes: readonly PdfPageSize[],
  pageNumber: number,
): PdfPageSize | null {
  if (pageSizes.length === 0) return null;
  const index = Math.min(pageSizes.length - 1, Math.max(0, Math.round(pageNumber) - 1));
  return pageSizes[index];
}

export type PdfLaidOutPage = {
  page: number;
  top: number;
  height: number;
};

/**
 * Page that occupies the most of the visible well. A tie goes to the page
 * that contains the vertical center of the viewport.
 */
export function pageWithMostVisibleArea(
  pages: readonly PdfLaidOutPage[],
  viewport: { scrollTop: number; height: number },
): number {
  if (pages.length === 0) return 1;
  const viewTop = viewport.scrollTop;
  const viewBottom = viewTop + viewport.height;
  const viewCenter = viewTop + viewport.height / 2;
  let bestPage = pages[0].page;
  let bestVisible = -1;
  let bestContainsCenter = false;
  for (const item of pages) {
    const pageBottom = item.top + item.height;
    const visible = Math.max(0, Math.min(viewBottom, pageBottom) - Math.max(viewTop, item.top));
    const containsCenter = item.top <= viewCenter && viewCenter < pageBottom;
    if (visible > bestVisible + 0.5 || (Math.abs(visible - bestVisible) <= 0.5 && containsCenter && !bestContainsCenter)) {
      bestVisible = visible;
      bestPage = item.page;
      bestContainsCenter = containsCenter;
    }
  }
  return bestPage;
}

/**
 * Calculate a fit scale for the supplied page sizes. Passing one page fits that
 * page; passing several uses bounds that fit every supplied page.
 */
export function fitScaleFor(
  mode: PdfFitMode,
  pageSizes: readonly PdfPageSize[],
  containerSize: { width: number; height: number },
): number {
  if (pageSizes.length === 0) return 1;

  const availW = Math.max(80, containerSize.width - PDF_CANVAS_PAD_X);
  const availH = Math.max(80, containerSize.height - PDF_CANVAS_PAD_Y);
  const { maxWidth, maxHeight } = pageSizes.reduce(
    (bounds, page) => ({
      maxWidth: Math.max(bounds.maxWidth, page.width),
      maxHeight: Math.max(bounds.maxHeight, page.height),
    }),
    { maxWidth: 0, maxHeight: 0 },
  );

  if (mode === 'fit-width') {
    return clampPdfFitZoom(availW / maxWidth);
  }

  return clampPdfFitZoom(Math.min(availW / maxWidth, availH / maxHeight));
}

/**
 * Visible padding box for fit math. `clientWidth` / `clientHeight` already
 * exclude classic scrollbars and `scrollbar-gutter`, including a stable
 * block-end gutter that the border box still reports.
 */
export function pdfFitViewport(container: HTMLElement): { width: number; height: number } {
  return {
    width: Math.max(80, container.clientWidth),
    height: Math.max(80, container.clientHeight),
  };
}

/**
 * Scroll offset that places a page in the middle of the visible page well.
 * `pageTopInView` is the page's top relative to the well (bounding-rect
 * delta), not `offsetTop` — that can include the viewer header/toolbar.
 */
export function scrollTopToCenterPage(
  scrollTop: number,
  pageTopInView: number,
  pageHeight: number,
  viewportHeight: number,
): number {
  const desiredTop = (viewportHeight - pageHeight) / 2;
  return Math.max(0, scrollTop + pageTopInView - desiredTop);
}

/**
 * Top/bottom padding so a fitted page can sit in the middle of the pane.
 * Page 1 cannot scroll above 0, so the gutter has to be real padding.
 */
export function fitPageCenterPadding(
  viewportHeight: number,
  pageHeight: number,
  minPad = PDF_CANVAS_EDGE_PAD,
): number {
  return Math.max(minPad, (viewportHeight - pageHeight) / 2);
}

export function nextRotationCcw(rotation: number): PdfRotation {
  return (((rotation + 270) % 360) + 360) % 360 as PdfRotation;
}

/** Visual width/height after a CSS `rotate(rotation deg)` around the page center. */
export function visualPageSize(page: PdfPageSize, rotation: number): PdfPageSize {
  return rotation % 180 === 0 ? page : { width: page.height, height: page.width };
}

/**
 * Map a top-left page-space point onto the unrotated-to-rotated wrapper.
 * CSS `rotate()` is clockwise; 270 is one counterclockwise step from 0.
 */
export function pagePointToVisualFraction(
  x: number,
  y: number,
  pageWidth: number,
  pageHeight: number,
  rotation: number,
): { fx: number; fy: number } {
  const px = pageWidth ? x / pageWidth : 0;
  const py = pageHeight ? y / pageHeight : 0;
  switch ((((rotation % 360) + 360) % 360)) {
    case 90:
      return { fx: 1 - py, fy: px };
    case 180:
      return { fx: 1 - px, fy: 1 - py };
    case 270:
      return { fx: py, fy: 1 - px };
    default:
      return { fx: px, fy: py };
  }
}

/** Pixel size of a sidebar thumbnail for a PDF page at `PDF_THUMB_WIDTH`. */
export function thumbnailSizeFor(
  page: PdfPageSize,
  thumbWidth = PDF_THUMB_WIDTH,
): PdfPageSize {
  const scale = thumbWidth / Math.max(1, page.width);
  return {
    width: Math.max(1, Math.round(page.width * scale)),
    height: Math.max(1, Math.round(page.height * scale)),
  };
}
