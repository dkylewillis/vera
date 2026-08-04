export type PdfPageSize = {
  width: number;
  height: number;
};

export type PdfFitMode = 'fit-width' | 'fit-page';

const PDF_ZOOM_MAX = 2.5;
/** Padding inside `.pdfCanvasWrap` (16px on each edge). */
const PDF_CANVAS_PAD_X = 32;
const PDF_CANVAS_PAD_Y = 32;

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
