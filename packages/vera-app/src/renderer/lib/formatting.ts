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

/** Inverse of {@link defaultVeraPath}: `manual.vera` → `manual.pdf`. */
export function siblingPdfPath(veraPath: string): string {
  const trimmed = veraPath.trim();
  if (!trimmed.toLowerCase().endsWith('.vera')) return '';
  return `${trimmed.slice(0, -5)}.pdf`;
}

export function sameFsPath(left: string, right: string): boolean {
  const normalize = (value: string) => value.replace(/\\/g, '/').replace(/\/+$/, '').toLowerCase();
  return normalize(left) === normalize(right);
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
  mode: 'batch';
  batchDirectory?: string;
}

function parentDirectory(filePath: string): string {
  return filePath.replace(/[/\\][^/\\]+$/, '');
}

/** Prefill Convert PDF directory fields from the latest Explorer selection. */
export function convertDefaultsFromSelection(
  selection: ExplorerSelection | null,
  fallbackFolderPath = '',
): ConvertPathDefaults | null {
  if (selection?.kind === 'file') {
    const batchDirectory = parentDirectory(selection.path);
    if (batchDirectory) return { mode: 'batch', batchDirectory };
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
