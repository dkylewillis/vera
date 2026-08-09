import { describe, expect, it } from 'vitest';
import { convertDefaultsFromSelection, showInFolderLabel } from './formatting';

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
