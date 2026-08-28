import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { describe, expect, it } from 'vitest';

import { folderRelativePath, listFolderEntries } from './folder-listing.js';

describe('folderRelativePath', () => {
  it('uses path.relative and posix separators', () => {
    expect(folderRelativePath(join('library', 'docs'), join('library', 'docs', 'sub', 'a.vera'))).toBe(
      'sub/a.vera',
    );
  });
});

describe('listFolderEntries', () => {
  it('returns null for a missing directory', () => {
    expect(listFolderEntries(join(tmpdir(), 'vera-missing-folder-listing'))).toBeNull();
  });

  it('includes nested files beyond five levels and reports truncation at the cap', () => {
    const root = mkdtempSync(join(tmpdir(), 'vera-folder-listing-'));
    let current = root;
    for (let depth = 1; depth <= 6; depth += 1) {
      current = join(current, `d${depth}`);
      mkdirSync(current);
    }
    writeFileSync(join(root, 'root.vera'), '');
    writeFileSync(join(current, 'deep.vera'), '');
    writeFileSync(join(root, 'skip.txt'), '');
    writeFileSync(join(root, 'notes.md'), '# Notes\n');

    const listed = listFolderEntries(root);
    expect(listed).not.toBeNull();
    expect(listed?.truncated).toBe(false);
    expect(listed?.entries.map((entry) => entry.relativePath)).toEqual([
      'd1/d2/d3/d4/d5/d6/deep.vera',
      'notes.md',
      'root.vera',
    ]);
    expect(listed?.entries.find((entry) => entry.relativePath === 'notes.md')?.type).toBe('md');

    const capped = listFolderEntries(root, 2);
    expect(capped?.truncated).toBe(true);
    expect(capped?.entries.map((entry) => entry.relativePath)).toEqual(['notes.md', 'root.vera']);
  });
});
