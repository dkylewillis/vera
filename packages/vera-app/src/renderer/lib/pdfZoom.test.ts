import { describe, expect, it } from 'vitest';

import { fitScaleFor, pageSizeForNumber } from './pdfZoom';

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
