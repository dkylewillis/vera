import { describe, expect, it } from 'vitest';
import { convertDefaultsFromSelection, defaultVeraPath, showInFolderLabel } from './formatting';

describe('showInFolderLabel', () => {
  it('uses platform-specific wording', () => {
    expect(showInFolderLabel('win32')).toBe('Show in Explorer');
    expect(showInFolderLabel('darwin')).toBe('Reveal in Finder');
    expect(showInFolderLabel('linux')).toBe('Show in Folder');
  });
});

describe('convertDefaultsFromSelection', () => {
  it('prefills single-PDF mode from a selected PDF', () => {
    expect(convertDefaultsFromSelection({ kind: 'file', type: 'pdf', path: 'C:\\docs\\manual.pdf' })).toEqual({
      mode: 'single',
      pdfPath: 'C:\\docs\\manual.pdf',
      outputPath: defaultVeraPath('C:\\docs\\manual.pdf'),
    });
  });

  it('suggests a sibling PDF for a selected .vera archive', () => {
    expect(convertDefaultsFromSelection({ kind: 'file', type: 'vera', path: 'C:\\docs\\manual.vera' })).toEqual({
      mode: 'single',
      pdfPath: 'C:\\docs\\manual.pdf',
      outputPath: 'C:\\docs\\manual.vera',
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
