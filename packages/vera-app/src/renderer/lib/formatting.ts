import type { SourceDocumentResult } from '../types';

export function fileName(filePath: string): string {
  return filePath.split(/[\\/]/).pop() || filePath;
}

export function formatBytes(value?: number | null): string {
  if (value === undefined || value === null) return '-';
  if (value < 1024) return `${value} B`;
  const units = ['KB', 'MB', 'GB', 'TB'];
  let amount = value / 1024;
  let unit = units[0];
  for (let index = 1; index < units.length && amount >= 1024; index += 1) {
    amount /= 1024;
    unit = units[index];
  }
  return `${amount >= 10 ? amount.toFixed(1) : amount.toFixed(2)} ${unit}`;
}

export function formatTimestamp(value?: string | null): string {
  if (!value) return '-';
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

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

export function siblingSourcePath(veraPath: string, sourceFileName?: string | null): string {
  const trimmed = veraPath.trim();
  if (!trimmed.toLowerCase().endsWith('.vera')) return '';
  const cut = Math.max(trimmed.lastIndexOf('/'), trimmed.lastIndexOf('\\'));
  const dir = cut >= 0 ? trimmed.slice(0, cut + 1) : '';
  if (sourceFileName?.trim()) return `${dir}${sourceFileName.trim()}`;
  return `${trimmed.slice(0, -5)}.pdf`;
}

/** `manual.vera` → `manual.pdf`. */
export function siblingPdfPath(veraPath: string): string {
  return siblingSourcePath(veraPath);
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

export function isMarkdownSource(source: SourceDocumentResult | null): boolean {
  if (!source) return false;
  const mime = source.mime_type.toLowerCase();
  const name = source.filename.toLowerCase();
  return mime === 'text/markdown'
    || mime === 'text/x-markdown'
    || name.endsWith('.md')
    || name.endsWith('.markdown');
}

export function showInFolderLabel(platform: string): string {
  if (platform === 'darwin') return 'Reveal in Finder';
  if (platform === 'win32') return 'Show in Explorer';
  return 'Show in Folder';
}

export type ExplorerSelection =
  | { kind: 'file'; path: string; type: 'vera' | 'pdf' | 'md' }
  | { kind: 'folder'; path: string };

export interface ConvertPathDefaults {
  mode: 'batch';
  batchDirectory?: string;
}

function parentDirectory(filePath: string): string {
  return filePath.replace(/[/\\][^/\\]+$/, '');
}

/** Prefill Convert directory fields from the latest Explorer selection. */
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
