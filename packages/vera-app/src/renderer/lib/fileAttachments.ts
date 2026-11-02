import type { AttachmentUsage, ChatAttachment, ChatCitationResult, ChatFileAttachment, Session, SessionTurn } from '../types';
import { folderEntryType, type FolderEntryType } from '../../shared/source-types';

export const DOCUMENT_EXTENSIONS = ['pdf', 'docx', 'pptx', 'xlsx', 'md', 'markdown', 'html', 'htm', 'txt', 'vera'] as const;

const DOCUMENT_SET = new Set<string>(DOCUMENT_EXTENSIONS);

export function fileExtension(name: string): string {
  const base = name.split(/[\\/]/).pop() || name;
  const dot = base.lastIndexOf('.');
  return dot >= 0 ? base.slice(dot + 1).toLowerCase() : '';
}

export function isDocumentAttachment(file: { name: string; type?: string }): boolean {
  if (file.type?.startsWith('image/')) return false;
  return DOCUMENT_SET.has(fileExtension(file.name));
}

export function isImageAttachment(file: { name: string; type?: string }): boolean {
  return Boolean(file.type?.startsWith('image/'));
}

export function splitDroppedFiles<T extends { name: string; type?: string }>(files: T[]): {
  images: T[];
  documents: T[];
  rejected: string[];
} {
  const images: T[] = [];
  const documents: T[] = [];
  const rejected: string[] = [];
  for (const file of files) {
    if (isImageAttachment(file)) images.push(file);
    else if (isDocumentAttachment(file)) documents.push(file);
    else rejected.push(file.name);
  }
  return { images, documents, rejected };
}

export function fileIconType(name: string): FolderEntryType {
  return folderEntryType(name) ?? 'md';
}

/** Attachment ids that should be placed in the prompt in full on this turn. */
export function fullAttachmentIds(files: ChatFileAttachment[], turns: SessionTurn[]): string[] {
  const latest = [...turns].reverse().find((turn) => turn.role === 'assistant');
  const cited = new Set(
    (latest?.citations ?? [])
      .map((citation: ChatCitationResult) => citation.result?.file)
      .filter((file): file is string => Boolean(file)),
  );
  return files.filter((file) => file.fresh || cited.has(file.vera_path)).map((file) => file.id);
}

/**
 * Next free `[A#]` number, after every range already given to this chat's files.
 * Files saved without `label_start` are numbered back to back, as the sidecar does.
 */
export function nextLabelStart(
  files: Array<Pick<ChatFileAttachment, 'label_start' | 'chunk_count' | 'vera_path'>>,
): number {
  let next = 1;
  for (const file of files) {
    if (!file.vera_path) continue;
    const start = file.label_start && file.label_start > 0 ? file.label_start : next;
    next = Math.max(next, start + Math.max(file.chunk_count, 1));
  }
  return next;
}

export function usageLabel(usage?: AttachmentUsage): string {
  if (!usage) return '';
  if (usage.delivery === 'full') return 'Read in full';
  if (usage.searches > 0) return `Searched ${usage.searches}×`;
  return 'Not used';
}

export function restoredChatAttachments(session: Pick<Session, 'file_attachments' | 'image_attachments'>): {
  files: ChatFileAttachment[];
  images: ChatAttachment[];
} {
  return {
    files: session.file_attachments ?? [],
    images: session.image_attachments ?? [],
  };
}

export function latestAttachmentUsage(turns: SessionTurn[]): Record<string, AttachmentUsage> | undefined {
  const latest = [...turns].reverse().find((turn) => turn.role === 'assistant' && turn.attachment_usage);
  return latest?.attachment_usage;
}
