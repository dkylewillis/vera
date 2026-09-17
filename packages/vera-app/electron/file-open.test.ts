import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

import { veraArchivePathFromArgs } from './file-open.js';

describe('veraArchivePathFromArgs', () => {
  it('finds a Windows shell file argument after Electron launch arguments', () => {
    expect(veraArchivePathFromArgs([
      'C:\\Program Files\\VERA\\VERA.exe',
      'C:\\Users\\me\\Desktop\\manual.vera',
    ])).toBe(resolve('C:\\Users\\me\\Desktop\\manual.vera'));
  });

  it('accepts a quoted, case-insensitive archive path', () => {
    expect(veraArchivePathFromArgs(['electron', '.', '"C:\\Docs\\Manual.VERA"']))
      .toBe(resolve('C:\\Docs\\Manual.VERA'));
  });

  it('ignores unrelated arguments', () => {
    expect(veraArchivePathFromArgs(['electron', '.', '--inspect', 'manual.pdf'])).toBeNull();
  });
});
