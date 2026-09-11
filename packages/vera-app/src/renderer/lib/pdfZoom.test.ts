import { describe, expect, it } from 'vitest';

import { fitPageCenterPadding, fitScaleFor, nextRotationCcw, pagePointToVisualFraction, pageSizeForNumber, pageWithMostVisibleArea, pdfFitViewport, scrollTopToCenterPage, thumbnailSizeFor, visualPageSize } from './pdfZoom';

describe('fitScaleFor', () => {
  it('fits the supplied active page width', () => {
    const pages = [
      { width: 600, height: 800 },
      { width: 800, height: 600 },
    ];
    const activePage = pageSizeForNumber(pages, 1);

    const scale = fitScaleFor('fit-width', [activePage!], { width: 632, height: 900 });

    expect(scale).toBe(1);
  });

  it('uses both widest and tallest pages for document fit-page', () => {
    const pages = [
      { width: 800, height: 600 },
      { width: 600, height: 1200 },
    ];

    const scale = fitScaleFor('fit-page', pages, { width: 832, height: 1032 });

    expect(scale).toBeCloseTo(5 / 6);
    expect(pages.every((page) => page.width * scale <= 800)).toBe(true);
    expect(pages.every((page) => page.height * scale <= 1000)).toBe(true);
  });

  it('caps enlargement without preventing very wide pages from fitting', () => {
    const page = [{ width: 100, height: 100 }];

    expect(fitScaleFor('fit-width', page, { width: 1032, height: 800 })).toBe(2.5);
    expect(fitScaleFor('fit-width', page, { width: 40, height: 80 })).toBe(0.8);
    expect(fitScaleFor('fit-width', [{ width: 1000, height: 1000 }], { width: 132, height: 800 })).toBe(0.1);
  });

  it('returns the default scale until page metadata is available', () => {
    expect(fitScaleFor('fit-width', [], { width: 800, height: 600 })).toBe(1);
  });

  it('scales a tall page so it fits the client height minus canvas padding', () => {
    const scale = fitScaleFor('fit-page', [{ width: 600, height: 1200 }], { width: 632, height: 832 });

    expect(scale).toBeCloseTo(800 / 1200);
    expect(600 * scale).toBeLessThanOrEqual(600);
    expect(1200 * scale).toBeLessThanOrEqual(800);
  });
});

describe('pdfFitViewport', () => {
  it('uses the client box so scrollbars and gutter are already excluded', () => {
    const container = {
      clientWidth: 632,
      clientHeight: 884,
    } as HTMLElement;

    expect(pdfFitViewport(container)).toEqual({ width: 632, height: 884 });
    expect(fitScaleFor('fit-width', [{ width: 600, height: 800 }], pdfFitViewport(container))).toBe(1);
  });
});

describe('scrollTopToCenterPage', () => {
  it('keeps a page that already sits in the middle of the well', () => {
    expect(scrollTopToCenterPage(0, 16, 800, 832)).toBe(0);
  });

  it('scrolls using the visible well, not a header offset', () => {
    expect(scrollTopToCenterPage(0, 216, 400, 832)).toBe(0);
    expect(scrollTopToCenterPage(0, 400, 400, 832)).toBe(184);
  });
});

describe('fitPageCenterPadding', () => {
  it('keeps the default edge pad when the page already fills the pane', () => {
    expect(fitPageCenterPadding(832, 800)).toBe(16);
  });

  it('adds extra pad so a shorter page can sit in the middle', () => {
    expect(fitPageCenterPadding(832, 400)).toBe(216);
  });
});

describe('rotation helpers', () => {
  it('steps counterclockwise in 90 degree increments', () => {
    expect(nextRotationCcw(0)).toBe(270);
    expect(nextRotationCcw(270)).toBe(180);
    expect(nextRotationCcw(180)).toBe(90);
    expect(nextRotationCcw(90)).toBe(0);
  });

  it('swaps width and height for quarter turns', () => {
    expect(visualPageSize({ width: 612, height: 792 }, 0)).toEqual({ width: 612, height: 792 });
    expect(visualPageSize({ width: 612, height: 792 }, 270)).toEqual({ width: 792, height: 612 });
  });

  it('maps a page-space point onto the rotated wrapper', () => {
    expect(pagePointToVisualFraction(0, 0, 100, 200, 0)).toEqual({ fx: 0, fy: 0 });
    expect(pagePointToVisualFraction(0, 0, 100, 200, 270)).toEqual({ fx: 0, fy: 1 });
    expect(pagePointToVisualFraction(0, 0, 100, 200, 90)).toEqual({ fx: 1, fy: 0 });
  });
});

describe('pageWithMostVisibleArea', () => {
  const pages = [
    { page: 1, top: 0, height: 400 },
    { page: 2, top: 416, height: 400 },
  ];

  it('picks the page that covers the most of the viewport', () => {
    expect(pageWithMostVisibleArea(pages, { scrollTop: 200, height: 500 })).toBe(2);
  });

  it('breaks a tie with the page under the viewport center', () => {
    const split = [
      { page: 1, top: 0, height: 400 },
      { page: 2, top: 400, height: 400 },
    ];
    expect(pageWithMostVisibleArea(split, { scrollTop: 200, height: 400 })).toBe(2);
  });

  it('returns page 1 when layout is empty', () => {
    expect(pageWithMostVisibleArea([], { scrollTop: 0, height: 800 })).toBe(1);
  });
});

describe('pageSizeForNumber', () => {
  const pages = [
    { width: 600, height: 800 },
    { width: 800, height: 600 },
  ];

  it('selects the active page and clamps out-of-range page numbers', () => {
    expect(pageSizeForNumber(pages, 2)).toBe(pages[1]);
    expect(pageSizeForNumber(pages, 99)).toBe(pages[1]);
    expect(pageSizeForNumber(pages, 0)).toBe(pages[0]);
  });

  it('returns null before page metadata is available', () => {
    expect(pageSizeForNumber([], 1)).toBeNull();
  });
});

describe('thumbnailSizeFor', () => {
  it('fits the thumbnail rail width and keeps the page aspect ratio', () => {
    expect(thumbnailSizeFor({ width: 612, height: 792 }, 88)).toEqual({
      width: 88,
      height: 114,
    });
  });
});
