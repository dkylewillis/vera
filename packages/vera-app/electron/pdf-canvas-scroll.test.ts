import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const styles = resolve(
  dirname(fileURLToPath(import.meta.url)),
  '../src/renderer/styles.css',
);

describe('pdf page well', () => {
  it('scrolls sideways when a sheet is wider than the view', () => {
    const css = readFileSync(styles, 'utf8');
    const start = css.indexOf('.pdfCanvasWrap {');
    const end = css.indexOf('.pdfCanvasWrap--fitPage');
    const block = css.slice(start, end);
    expect(start).toBeGreaterThan(-1);
    expect(block).toContain('overflow-x: auto');
    expect(block).not.toContain('overflow-x: hidden');
  });

  it('rotates the selectable text layer with the stored page rotation', () => {
    const css = readFileSync(styles, 'utf8');
    const start = css.indexOf('.textLayer {');
    const end = css.indexOf('.textLayer span');
    const block = css.slice(start, end);
    expect(start).toBeGreaterThan(-1);
    expect(block).toContain('transform-origin: 0 0');
    expect(block).toContain('[data-main-rotation=\'90\']');
    expect(block).toContain('rotate(90deg) translateY(-100%)');
    expect(block).toContain('[data-main-rotation=\'180\']');
    expect(block).toContain('rotate(180deg) translate(-100%, -100%)');
    expect(block).toContain('[data-main-rotation=\'270\']');
    expect(block).toContain('rotate(270deg) translateX(-100%)');
  });
});
