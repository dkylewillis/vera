import { describe, expect, it } from 'vitest';
import { convertDefaultsFromSelection, fileName, formatBytes, formatTimestamp, isPathInsideFolder, sameFsPath, siblingPdfPath, showInFolderLabel } from './formatting';

describe('showInFolderLabel', () => {
  it('uses platform-specific wording', () => {
    expect(showInFolderLabel('win32')).toBe('Show in Explorer');
    expect(showInFolderLabel('darwin')).toBe('Reveal in Finder');
    expect(showInFolderLabel('linux')).toBe('Show in Folder');
  });
});

describe('convertDefaultsFromSelection', () => {
  it('prefills directory mode from a selected PDF parent folder', () => {
    expect(convertDefaultsFromSelection({ kind: 'file', type: 'pdf', path: 'C:\\docs\\manual.pdf' })).toEqual({
      mode: 'batch',
      batchDirectory: 'C:\\docs',
    });
  });

  it('prefills directory mode from a selected .vera parent folder', () => {
    expect(convertDefaultsFromSelection({ kind: 'file', type: 'vera', path: 'C:\\docs\\manual.vera' })).toEqual({
      mode: 'batch',
      batchDirectory: 'C:\\docs',
    });
  });

  it('prefills directory mode from a selected folder', () => {
    expect(convertDefaultsFromSelection({ kind: 'folder', path: 'C:\\proposals' })).toEqual({
      mode: 'batch',
      batchDirectory: 'C:\\proposals',
    });
  });

  it('falls back to the active library folder', () => {
    expect(convertDefaultsFromSelection(null, 'C:\\library')).toEqual({
      mode: 'batch',
      batchDirectory: 'C:\\library',
    });
  });

  it('returns null when nothing is selected', () => {
    expect(convertDefaultsFromSelection(null)).toBeNull();
  });
});

describe('siblingPdfPath', () => {
  it('maps a .vera archive to the same-named PDF', () => {
    expect(siblingPdfPath('C:\\docs\\manual.vera')).toBe('C:\\docs\\manual.pdf');
  });

  it('returns empty for non-archive paths', () => {
    expect(siblingPdfPath('manual.pdf')).toBe('');
  });
});

describe('sameFsPath', () => {
  it('ignores slash style and case', () => {
    expect(sameFsPath('C:\\docs\\Manual.PDF', 'c:/docs/manual.pdf')).toBe(true);
  });
});

describe('isPathInsideFolder', () => {
  it('matches the folder itself and nested files', () => {
    expect(isPathInsideFolder('C:\\library', 'C:\\library')).toBe(true);
    expect(isPathInsideFolder('C:\\library\\manual.vera', 'C:\\library')).toBe(true);
    expect(isPathInsideFolder('C:\\library\\nested\\manual.pdf', 'C:\\library')).toBe(true);
  });

  it('does not match a sibling path with a shared prefix', () => {
    expect(isPathInsideFolder('C:\\library-old\\manual.vera', 'C:\\library')).toBe(false);
    expect(isPathInsideFolder('C:\\other\\manual.pdf', 'C:\\library')).toBe(false);
  });
});

describe('fileName', () => {
  it('returns the last path segment', () => {
    expect(fileName('C:\\docs\\manual.vera')).toBe('manual.vera');
    expect(fileName('/library/manual.pdf')).toBe('manual.pdf');
    expect(fileName('manual.vera')).toBe('manual.vera');
  });
});

describe('formatBytes', () => {
  it('formats missing values', () => {
    expect(formatBytes()).toBe('-');
    expect(formatBytes(null)).toBe('-');
  });

  it('keeps small sizes in bytes', () => {
    expect(formatBytes(512)).toBe('512 B');
  });

  it('uses two decimals below 10 and one decimal at 10+', () => {
    expect(formatBytes(2048)).toBe('2.00 KB');
    expect(formatBytes(10240)).toBe('10.0 KB');
    expect(formatBytes(1048576)).toBe('1.00 MB');
  });
});

describe('formatTimestamp', () => {
  it('formats missing and invalid values', () => {
    expect(formatTimestamp()).toBe('-');
    expect(formatTimestamp('not-a-date')).toBe('not-a-date');
  });

  it('formats valid timestamps with the locale', () => {
    const value = '2024-01-15T12:00:00.000Z';
    expect(formatTimestamp(value)).toBe(new Date(value).toLocaleString());
  });
});
