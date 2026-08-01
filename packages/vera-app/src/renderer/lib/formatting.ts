import type { SourceDocumentResult } from '../types';

export function formatPages(start: number | null, end: number | null): string {
  if (start === null && end === null) return '-';
  if (start === end || end === null) return String(start);
  if (start === null) return String(end);
  return `${start}-${end}`;
}

export function formatBox(box: number[] | undefined): string {
  if (!box?.length) return '-';
  return box.map((value) => Math.round(value)).join(', ');
}

export function defaultVeraPath(pdf: string): string {
  const trimmed = pdf.trim();
  if (!trimmed) return '';
  return trimmed.toLowerCase().endsWith('.pdf') ? `${trimmed.slice(0, -4)}.vera` : `${trimmed}.vera`;
}

export function isPathInsideFolder(filePath: string, folderPath: string): boolean {
  const file = filePath.replace(/\\/g, '/').replace(/\/+$/, '').toLowerCase();
  const folder = folderPath.replace(/\\/g, '/').replace(/\/+$/, '').toLowerCase();
  return file === folder || file.startsWith(`${folder}/`);
}

export function isPdfSource(source: SourceDocumentResult | null): boolean {
  if (!source) return false;
  return source.mime_type === 'application/pdf' || source.filename.toLowerCase().endsWith('.pdf');
}

export function showInFolderLabel(platform: string): string {
  if (platform === 'darwin') return 'Reveal in Finder';
  if (platform === 'win32') return 'Show in Explorer';
  return 'Show in Folder';
}

export type ExplorerSelection =
  | { kind: 'file'; path: string; type: 'vera' | 'pdf' }
  | { kind: 'folder'; path: string };

export interface ConvertPathDefaults {
  mode: 'single' | 'batch';
  pdfPath?: string;
  outputPath?: string;
  batchDirectory?: string;
}

/** Prefill Convert PDF fields from the latest Explorer selection. */
export function convertDefaultsFromSelection(
  selection: ExplorerSelection | null,
  fallbackFolderPath = '',
): ConvertPathDefaults | null {
  if (selection?.kind === 'file' && selection.type === 'pdf') {
    return {
      mode: 'single',
      pdfPath: selection.path,
      outputPath: defaultVeraPath(selection.path),
    };
  }
  if (selection?.kind === 'file' && selection.type === 'vera') {
    return {
      mode: 'single',
      pdfPath: selection.path.replace(/\.vera$/i, '.pdf'),
      outputPath: selection.path,
    };
  }
  if (selection?.kind === 'folder') {
    return { mode: 'batch', batchDirectory: selection.path };
  }
  const folder = fallbackFolderPath.trim();
  if (folder) {
    return { mode: 'batch', batchDirectory: folder };
  }
  return null;
}
